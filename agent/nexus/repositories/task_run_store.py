# Proprietary and non-commercial use only.

"""Durable task/run lifecycle, leasing, stale-run recovery, and cancellation."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Literal

from firebase_admin import firestore
from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import FieldFilter

from nexus.production_tasks import (
    FIELD_CANCEL_REQUESTED,
    TERMINAL_TASK_STATUSES,
    BoundProductionStore,
    _coerce_datetime,
    _uuid,
    build_execution_payload,
    canonicalize_task_status,
    normalize_autonomy_mode,
    settings,
    utcnow,
)

logger = logging.getLogger(__name__)


class TaskRunStore(BoundProductionStore):
    async def create_task(
        self,
        *,
        owner_id: str,
        title: str,
        input_text: str = "",
        autonomy_mode: str | None = None,
        session_id: str | None = None,
        budget: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DurableTask:
        return await asyncio.to_thread(
            self._create_task_sync,
            owner_id,
            title,
            input_text,
            autonomy_mode,
            session_id,
            budget,
            metadata,
        )

    def _create_task_sync(
        self,
        owner_id: str,
        title: str,
        input_text: str,
        autonomy_mode: str | None,
        session_id: str | None,
        budget: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
    ) -> DurableTask:
        task_id = _uuid("task_")
        now = utcnow()
        payload = {
            "taskId": task_id,
            "ownerId": owner_id,
            "title": title.strip() or "Untitled task",
            "status": canonicalize_task_status("queued"),
            "autonomyMode": normalize_autonomy_mode(autonomy_mode or settings.default_autonomy_mode),
            "sessionId": session_id,
            "currentRunId": None,
            "inputText": input_text,
            "cancelRequested": False,
            "budget": budget
            or {
                "credits": settings.default_task_budget_credits,
                "maxRuntimeMinutes": settings.default_task_max_runtime_minutes,
                "maxToolCalls": settings.default_task_max_tool_calls,
            },
            "sandboxState": {"state": "none"},
            "metadata": metadata or {},
            "createdAt": now,
            "updatedAt": now,
        }
        self._task_ref(task_id).set(payload)
        return self._build_task(task_id, payload)

    async def create_run(
        self,
        *,
        task_id: str,
        owner_id: str,
        session_id: str | None = None,
        input_text: str | None = None,
        connector_ids: list[str] | None = None,
        tool_ids: list[str] | None = None,
        uploaded_files: list[dict[str, Any]] | None = None,
        runtime_config_snapshot: dict[str, Any] | None = None,
        autonomy_mode: str | None = None,
        budget: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DurableTaskRun:
        return await asyncio.to_thread(
            self._create_run_sync,
            task_id,
            owner_id,
            session_id,
            input_text,
            connector_ids,
            tool_ids,
            uploaded_files,
            runtime_config_snapshot,
            autonomy_mode,
            budget,
            metadata,
        )

    def _create_run_sync(
        self,
        task_id: str,
        owner_id: str,
        session_id: str | None,
        input_text: str | None,
        connector_ids: list[str] | None,
        tool_ids: list[str] | None,
        uploaded_files: list[dict[str, Any]] | None,
        runtime_config_snapshot: dict[str, Any] | None,
        autonomy_mode: str | None,
        budget: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
    ) -> DurableTaskRun:
        run_id = _uuid("run_")
        now = utcnow()
        task_doc = self._task_ref(task_id).get()
        if not task_doc.exists:
            logger.error(f"Cannot create run for non-existent task: {task_id}")
            raise ValueError(f"Task not found: {task_id}")
        task_data = task_doc.to_dict() or {}
        effective_input = input_text if input_text is not None else str(task_data.get("inputText") or "")
        effective_budget = budget if budget is not None else task_data.get("budget")
        if not isinstance(effective_budget, dict):
            effective_budget = {}
        effective_autonomy = autonomy_mode or str(task_data.get("autonomyMode") or settings.default_autonomy_mode)
        execution_payload = build_execution_payload(
            task_id=task_id,
            run_id=run_id,
            owner_id=owner_id,
            session_id=session_id,
            input_text=effective_input,
            connector_ids=connector_ids,
            tool_ids=tool_ids,
            uploaded_files=uploaded_files,
            runtime_config_snapshot=runtime_config_snapshot,
            autonomy_mode=effective_autonomy,
            budget=effective_budget,
            metadata=metadata,
        )
        payload = {
            "runId": run_id,
            "taskId": task_id,
            "ownerId": owner_id,
            "status": canonicalize_task_status("queued"),
            "attempt": 1,
            "claimToken": _uuid("claim_"),
            "claimGeneration": 0,
            "sessionId": session_id,
            "executionPayload": execution_payload,
            "checkpoint": {},
            "createdAt": now,
            "updatedAt": now,
        }
        batch = self._db.batch()
        batch.set(self._run_ref(task_id, run_id), payload)
        batch.set(
            self._task_ref(task_id),
            {
                "currentRunId": run_id,
                "status": canonicalize_task_status("queued"),
                "updatedAt": now,
                # A new run is new user intent, so a cancel aimed at a previous
                # run must not carry over. Leaving it set makes this run
                # unclaimable (see claim_run) and the task permanently dead.
                FIELD_CANCEL_REQUESTED: False,
            },
            merge=True,
        )
        try:
            batch.commit()
        except Exception as exc:
            logger.exception(f"Failed to commit run creation for task {task_id}")
            raise RuntimeError(f"Failed to commit run creation for task {task_id}: {exc}") from exc
        return self._build_run(run_id, payload)

    async def get_run(self, *, task_id: str, run_id: str, owner_id: str) -> DurableTaskRun | None:
        return await asyncio.to_thread(self._get_run_sync, task_id, run_id, owner_id)

    def _get_run_sync(self, task_id: str, run_id: str, owner_id: str) -> DurableTaskRun | None:
        doc = self._run_ref(task_id, run_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return None
        return self._build_run(run_id, data)

    async def claim_run(
        self,
        *,
        task_id: str,
        run_id: str,
        worker_id: str,
        claim_token: str | None = None,
    ) -> DurableTaskRun | None:
        return await asyncio.to_thread(
            self._claim_run_sync,
            task_id,
            run_id,
            worker_id,
            claim_token,
        )

    def _claim_run_sync(
        self,
        task_id: str,
        run_id: str,
        worker_id: str,
        claim_token: str | None = None,
    ) -> DurableTaskRun | None:
        now = utcnow()
        lease_expires_at = now + timedelta(seconds=settings.task_worker_lease_seconds)
        run_ref = self._run_ref(task_id, run_id)
        task_ref = self._task_ref(task_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_claim(txn):
            task_doc = task_ref.get(transaction=txn)
            run_doc = run_ref.get(transaction=txn)
            if not task_doc.exists or not run_doc.exists:
                return None
            task_data = task_doc.to_dict() or {}
            run_data = run_doc.to_dict() or {}
            expected_claim_token = str(run_data.get("claimToken") or "")
            if expected_claim_token and claim_token != expected_claim_token:
                logger.warning(
                    "Rejected stale or missing claim token for %s/%s",
                    task_id,
                    run_id,
                )
                return None
            if bool(task_data.get("cancelRequested")):
                return None
            status = canonicalize_task_status(str(run_data.get("status") or "queued"))
            existing_lease = _coerce_datetime(run_data.get("leaseExpiresAt"))
            if status == "running" and existing_lease and existing_lease > now:
                return None
            if status in {"completed", "failed", "cancelled"}:
                return None
            claim_generation = int(run_data.get("claimGeneration", 0) or 0) + 1
            updates = {
                "status": canonicalize_task_status("running"),
                "leaseOwner": worker_id,
                "leaseExpiresAt": lease_expires_at,
                "claimGeneration": claim_generation,
                "startedAt": run_data.get("startedAt") or now,
                "updatedAt": now,
            }
            txn.set(run_ref, updates, merge=True)
            txn.set(
                task_ref,
                {"status": canonicalize_task_status("running"), "currentRunId": run_id, "updatedAt": now},
                merge=True,
            )
            run_data.update(updates)
            return self._build_run(run_id, run_data)

        return transactional_claim(transaction)

    async def renew_lease(
        self,
        *,
        task_id: str,
        run_id: str,
        worker_id: str,
        claim_generation: int,
    ) -> bool:
        """Extend only the lease held by the current claim generation."""
        return await asyncio.to_thread(
            self._renew_lease_sync,
            task_id,
            run_id,
            worker_id,
            claim_generation,
        )

    def _renew_lease_sync(
        self,
        task_id: str,
        run_id: str,
        worker_id: str,
        claim_generation: int,
    ) -> bool:
        now = utcnow()
        run_ref = self._run_ref(task_id, run_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_renew(txn):
            run_doc = run_ref.get(transaction=txn)
            if not run_doc.exists:
                return False
            data = run_doc.to_dict() or {}
            if canonicalize_task_status(data.get("status")) != "running":
                return False
            if data.get("leaseOwner") != worker_id:
                return False
            if int(data.get("claimGeneration", 0) or 0) != int(claim_generation):
                return False
            txn.set(
                run_ref,
                {
                    "leaseExpiresAt": now
                    + timedelta(seconds=settings.task_worker_lease_seconds),
                    "lastHeartbeatAt": now,
                    "updatedAt": now,
                },
                merge=True,
            )
            return True

        return bool(transactional_renew(transaction))

    async def save_checkpoint(
        self,
        *,
        task_id: str,
        run_id: str,
        owner_id: str,
        checkpoint: dict[str, Any],
    ) -> bool:
        """Persist a bounded resumable checkpoint for a non-terminal run."""
        return await asyncio.to_thread(
            self._save_checkpoint_sync,
            task_id,
            run_id,
            owner_id,
            checkpoint,
        )

    def _save_checkpoint_sync(
        self,
        task_id: str,
        run_id: str,
        owner_id: str,
        checkpoint: dict[str, Any],
    ) -> bool:
        run_ref = self._run_ref(task_id, run_id)
        doc = run_ref.get()
        if not doc.exists:
            return False
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return False
        if canonicalize_task_status(data.get("status")) in TERMINAL_TASK_STATUSES:
            return False
        now = utcnow()
        clean_checkpoint = dict(checkpoint)
        clean_checkpoint["updated_at"] = now.isoformat()
        batch = self._db.batch()
        batch.set(
            run_ref,
            {"checkpoint": clean_checkpoint, "updatedAt": now},
            merge=True,
        )
        batch.set(
            self._task_ref(task_id),
            {"lastCheckpoint": clean_checkpoint, "updatedAt": now},
            merge=True,
        )
        batch.commit()
        return True

    async def pause_run(
        self,
        *,
        task_id: str,
        run_id: str,
        status: Literal["paused", "waiting_approval"],
        summary: str,
        checkpoint: dict[str, Any],
        verification: dict[str, Any] | None = None,
        final_response: str = "",
    ) -> None:
        await asyncio.to_thread(
            self._pause_run_sync,
            task_id,
            run_id,
            status,
            summary,
            checkpoint,
            verification,
            final_response,
        )

    def _pause_run_sync(
        self,
        task_id: str,
        run_id: str,
        status: str,
        summary: str,
        checkpoint: dict[str, Any],
        verification: dict[str, Any] | None,
        final_response: str,
    ) -> None:
        now = utcnow()
        run_ref = self._run_ref(task_id, run_id)
        current = run_ref.get()
        if current.exists:
            current_status = canonicalize_task_status(
                (current.to_dict() or {}).get("status")
            )
            if current_status in TERMINAL_TASK_STATUSES:
                return
        updates = {
            "status": canonicalize_task_status(status),
            "summary": summary,
            "checkpoint": checkpoint,
            "verification": verification or {},
            "finalResponse": final_response,
            "updatedAt": now,
            "leaseOwner": None,
            "leaseExpiresAt": None,
        }
        batch = self._db.batch()
        batch.set(run_ref, updates, merge=True)
        batch.set(
            self._task_ref(task_id),
            {
                "status": canonicalize_task_status(status),
                "lastSummary": summary,
                "lastCheckpoint": checkpoint,
                "lastVerification": verification or {},
                "updatedAt": now,
            },
            merge=True,
        )
        batch.commit()

    async def requeue_run(
        self,
        *,
        task_id: str,
        run_id: str,
        reason: str,
        expected_generation: int | None = None,
        worker_id: str | None = None,
    ) -> DurableTaskRun | None:
        """Atomically create the next bounded claim attempt."""
        return await asyncio.to_thread(
            self._requeue_run_sync,
            task_id,
            run_id,
            reason,
            expected_generation,
            worker_id,
        )

    def _requeue_run_sync(
        self,
        task_id: str,
        run_id: str,
        reason: str,
        expected_generation: int | None,
        worker_id: str | None,
    ) -> DurableTaskRun | None:
        now = utcnow()
        run_ref = self._run_ref(task_id, run_id)
        task_ref = self._task_ref(task_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_requeue(txn):
            run_doc = run_ref.get(transaction=txn)
            task_doc = task_ref.get(transaction=txn)
            if not run_doc.exists or not task_doc.exists:
                return None
            data = run_doc.to_dict() or {}
            task_data = task_doc.to_dict() or {}
            if bool(task_data.get("cancelRequested")):
                return None
            status = canonicalize_task_status(data.get("status"))
            if status in TERMINAL_TASK_STATUSES or status == "queued":
                return None
            generation = int(data.get("claimGeneration", 0) or 0)
            if expected_generation is not None and generation != int(expected_generation):
                return None
            lease_expiry = _coerce_datetime(data.get("leaseExpiresAt"))
            if worker_id:
                if data.get("leaseOwner") != worker_id:
                    return None
            elif status == "running" and lease_expiry and lease_expiry > now:
                return None
            attempt = int(data.get("attempt", 1) or 1)
            if attempt >= max(1, settings.task_worker_max_attempts):
                return None
            updates = {
                "status": canonicalize_task_status("queued"),
                "attempt": attempt + 1,
                "claimToken": _uuid("claim_"),
                "leaseOwner": None,
                "leaseExpiresAt": None,
                "lastRetryReason": reason[:1000],
                "updatedAt": now,
            }
            txn.set(run_ref, updates, merge=True)
            txn.set(
                task_ref,
                {
                    "status": canonicalize_task_status("queued"),
                    "currentRunId": run_id,
                    "updatedAt": now,
                },
                merge=True,
            )
            data.update(updates)
            return self._build_run(run_id, data)

        return transactional_requeue(transaction)

    async def list_stale_runs(self, *, limit: int = 100) -> list[DurableTaskRun]:
        return await asyncio.to_thread(self._list_stale_runs_sync, limit)

    def _list_stale_runs_sync(self, limit: int) -> list[DurableTaskRun]:
        now = utcnow()
        try:
            query = (
                self._db.collection_group("runs")
                .where(filter=FieldFilter("status", "==", "running"))
                .where(filter=FieldFilter("leaseExpiresAt", "<=", now))
                .limit(max(1, min(int(limit), 500)))
            )
            stale: list[DurableTaskRun] = []
            for doc in query.stream():
                stale.append(self._build_run(doc.id, doc.to_dict() or {}))
            return stale
        except FailedPrecondition as exc:
            message = str(exc).lower()
            is_missing_stale_runs_index = (
                "index" in message
                and "runs" in message
                and "leaseexpiresat" in message
            )
            if is_missing_stale_runs_index:
                if not getattr(self, "_stale_runs_index_warning_emitted", False):
                    self._stale_runs_index_warning_emitted = True
                    logger.warning(
                        "Skipping stale durable-run cleanup because Firestore index "
                        "runs(status ASC, leaseExpiresAt ASC) is missing or still building. "
                        "Deploy firestore.indexes.json and wait for the index to become READY; "
                        "further warnings are suppressed until process restart."
                    )
                return []
            logger.warning("Failed to query stale durable runs", exc_info=True)
            return []
        except Exception:
            logger.warning("Failed to query stale durable runs", exc_info=True)
            return []

    async def fail_stale_run(
        self,
        *,
        task_id: str,
        run_id: str,
        expected_generation: int,
        summary: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._fail_stale_run_sync,
            task_id,
            run_id,
            expected_generation,
            summary,
        )

    def _fail_stale_run_sync(
        self,
        task_id: str,
        run_id: str,
        expected_generation: int,
        summary: str,
    ) -> bool:
        now = utcnow()
        run_ref = self._run_ref(task_id, run_id)
        task_ref = self._task_ref(task_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_fail(txn):
            run_doc = run_ref.get(transaction=txn)
            if not run_doc.exists:
                return False
            data = run_doc.to_dict() or {}
            if canonicalize_task_status(data.get("status")) != "running":
                return False
            if int(data.get("claimGeneration", 0) or 0) != int(expected_generation):
                return False
            lease_expiry = _coerce_datetime(data.get("leaseExpiresAt"))
            if lease_expiry and lease_expiry > now:
                return False
            updates = {
                "status": canonicalize_task_status("failed"),
                "summary": summary,
                "error": summary,
                "completedAt": now,
                "updatedAt": now,
                "leaseOwner": None,
                "leaseExpiresAt": None,
            }
            txn.set(run_ref, updates, merge=True)
            txn.set(
                task_ref,
                {
                    "status": canonicalize_task_status("failed"),
                    "lastSummary": summary,
                    "updatedAt": now,
                },
                merge=True,
            )
            return True

        return bool(transactional_fail(transaction))

    async def finish_run(
        self,
        *,
        task_id: str,
        run_id: str,
        status: Literal["completed", "failed", "cancelled"],
        summary: str = "",
        error: str | None = None,
        verification: dict[str, Any] | None = None,
        checkpoint: dict[str, Any] | None = None,
        final_response: str = "",
    ) -> None:
        await asyncio.to_thread(
            self._finish_run_sync,
            task_id,
            run_id,
            status,
            summary,
            error,
            verification,
            checkpoint,
            final_response,
        )

    def _finish_run_sync(
        self,
        task_id: str,
        run_id: str,
        status: str,
        summary: str,
        error: str | None,
        verification: dict[str, Any] | None = None,
        checkpoint: dict[str, Any] | None = None,
        final_response: str = "",
    ) -> None:
        now = utcnow()
        updates = {
            "status": canonicalize_task_status(status),
            "summary": summary,
            "error": error,
            "completedAt": now,
            "updatedAt": now,
            "leaseOwner": None,
            "leaseExpiresAt": None,
            "verification": verification or {},
            "checkpoint": checkpoint or {},
            "finalResponse": final_response,
        }
        batch = self._db.batch()
        batch.set(self._run_ref(task_id, run_id), updates, merge=True)
        batch.set(
            self._task_ref(task_id),
            {
                "status": canonicalize_task_status(status),
                "updatedAt": now,
                "lastSummary": summary,
                "lastVerification": verification or {},
                "lastCheckpoint": checkpoint or {},
                "lastFinalResponse": final_response,
            },
            merge=True,
        )
        batch.commit()

    async def request_cancel(self, *, task_id: str, owner_id: str) -> bool:
        return await asyncio.to_thread(self._request_cancel_sync, task_id, owner_id)

    def _request_cancel_sync(self, task_id: str, owner_id: str) -> bool:
        task = self._get_task_sync(task_id)
        if not task or task.owner_id != owner_id:
            return False
        now = utcnow()
        self._task_ref(task_id).set(
            {"cancelRequested": True, "status": canonicalize_task_status("cancelling"), "updatedAt": now},
            merge=True,
        )
        self._append_event_sync(
            task_id,
            owner_id,
            "task_cancel_requested",
            {"status": "cancelling"},
            task.current_run_id,
            True,
        )
        return True

    async def clear_cancel_request(self, *, task_id: str, owner_id: str) -> bool:
        """Release a ``cancelRequested`` flag whose run has already settled.

        ``cancelRequested`` is checked by :meth:`claim_run` and
        :meth:`requeue_run`, both of which refuse outright while it is set. It is
        only meaningful for the run that was live when the user pressed stop, so
        leaving it on after that run is terminal makes every subsequent run on the
        task unclaimable — the session can never execute anything again.
        """
        return await asyncio.to_thread(
            self._clear_cancel_request_sync, task_id, owner_id
        )

    def _clear_cancel_request_sync(self, task_id: str, owner_id: str) -> bool:
        now = utcnow()
        task_ref = self._task_ref(task_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_clear(txn):
            task_doc = task_ref.get(transaction=txn)
            if not task_doc.exists:
                return False
            data = task_doc.to_dict() or {}
            if data.get("ownerId") != owner_id:
                return False
            if not bool(data.get(FIELD_CANCEL_REQUESTED)):
                return False
            run_id = data.get("currentRunId")
            if isinstance(run_id, str) and run_id:
                # Refuse while the targeted run may still act on the flag.
                run_doc = self._run_ref(task_id, run_id).get(transaction=txn)
                if run_doc.exists:
                    run_data = run_doc.to_dict() or {}
                    status = canonicalize_task_status(run_data.get("status"))
                    if status not in TERMINAL_TASK_STATUSES:
                        return False
            updates = {FIELD_CANCEL_REQUESTED: False, "updatedAt": now}
            current_status = canonicalize_task_status(data.get("status"))
            if current_status == "cancelling":
                updates["status"] = canonicalize_task_status("cancelled")
            txn.set(task_ref, updates, merge=True)
            return True

        cleared = bool(transactional_clear(transaction))
        if cleared:
            logger.info("Cleared stale cancel request on task %s", task_id)
        return cleared
