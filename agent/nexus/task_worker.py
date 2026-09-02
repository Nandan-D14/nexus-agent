# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Lease-owned durable task worker with bounded crash recovery."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import socket
from dataclasses import dataclass, field
from typing import Any

from nexus.agent_turn_runner import AgentTurnRequest, AgentTurnRunner
from nexus.config import settings
from nexus.dependencies import get_production_task_repository, get_session_manager
from nexus.production_tasks import TERMINAL_TASK_STATUSES, lease_is_live


logger = logging.getLogger(__name__)


@dataclass
class WorkerRunResult:
    status: str
    summary: str
    final_response: str = ""
    verification: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False


class TaskWorker:
    """Own one claim generation and renew it until the turn terminates."""

    def __init__(self, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"{socket.gethostname()}-worker"

    async def run_once(
        self,
        *,
        task_id: str,
        run_id: str,
        claim_token: str | None = None,
    ) -> WorkerRunResult:
        repo = get_production_task_repository()
        claimed = await repo.claim_run(
            task_id=task_id,
            run_id=run_id,
            worker_id=self.worker_id,
            claim_token=claim_token,
        )
        # #region agent log
        try:
            import json as _dbg_json
            from pathlib import Path as _DbgPath
            _DbgPath(r"C:\Users\nanda\OneDrive\Desktop\co-computer\debug-2a93a8.log").open("a", encoding="utf-8").write(_dbg_json.dumps({"sessionId":"2a93a8","hypothesisId":"C","location":"task_worker.py:claim","message":"claim_run result","data":{"task_id":task_id,"run_id":run_id,"claimed":bool(claimed),"worker_id":self.worker_id},"timestamp":int(__import__("time").time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        if not claimed:
            # A skipped claim produces no events at all, so the UI would wait on
            # a run that will never execute. Record why it was rejected and, when
            # nobody else owns the run, settle it so the client stops waiting.
            await self._report_claim_rejection(
                repo=repo,
                task_id=task_id,
                run_id=run_id,
            )
            return WorkerRunResult(
                "skipped",
                "Run is stale, already leased, cancelled, missing, or complete.",
            )

        generation = int(getattr(claimed, "claim_generation", 0) or 0)
        await repo.append_event(
            task_id=task_id,
            owner_id=claimed.owner_id,
            run_id=run_id,
            event_type="worker_claimed",
            payload={
                "worker_id": self.worker_id,
                "attempt": int(getattr(claimed, "attempt", 1) or 1),
                "claim_generation": generation,
            },
        )

        heartbeat = asyncio.create_task(
            self._lease_heartbeat(
                repo=repo,
                task_id=task_id,
                run_id=run_id,
                claim_generation=generation,
            ),
            name=f"lease-heartbeat-{task_id}-{run_id}",
        )
        try:
            execution = asyncio.create_task(
                self._execute_claimed_run(
                    task_id=task_id,
                    run_id=run_id,
                    owner_id=claimed.owner_id,
                ),
                name=f"durable-execution-{task_id}-{run_id}",
            )
            done, _ = await asyncio.wait(
                {execution, heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat in done:
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                heartbeat_error = heartbeat.exception()
                raise heartbeat_error or RuntimeError(
                    "Durable worker lease heartbeat stopped."
                )
            result = await execution

            verification_code = str(
                (result.verification or {}).get("error_code") or ""
            )
            if (
                result.status == "partial"
                and result.retryable
                and verification_code == "SUBAGENTS_PENDING"
                and await self._wait_for_durable_subagents(
                    repo=repo,
                    claimed=claimed,
                )
            ):
                retried = await self._retry_claimed_run(
                    repo=repo,
                    claimed=claimed,
                    reason=(
                        "Durable subagents settled; resume parent synthesis."
                    ),
                )
                if retried:
                    return WorkerRunResult(
                        "retrying",
                        result.summary,
                        final_response=result.final_response,
                        verification=result.verification,
                        checkpoint=result.checkpoint,
                        retryable=True,
                    )
            if result.status in {"partial", "blocked"}:
                pause_status = (
                    "waiting_approval"
                    if result.status == "blocked"
                    else "paused"
                )
                await repo.pause_run(
                    task_id=task_id,
                    run_id=run_id,
                    status=pause_status,
                    summary=result.summary,
                    checkpoint=result.checkpoint,
                    verification=result.verification,
                    final_response=result.final_response,
                )
            elif result.status == "completed":
                await repo.finish_run(
                    task_id=task_id,
                    run_id=run_id,
                    status="completed",
                    summary=result.summary,
                    verification=result.verification,
                    checkpoint=result.checkpoint,
                    final_response=result.final_response,
                )
            elif result.status == "cancelled":
                await repo.finish_run(
                    task_id=task_id,
                    run_id=run_id,
                    status="cancelled",
                    summary=result.summary,
                    error=result.summary,
                    verification=result.verification,
                    checkpoint=result.checkpoint,
                    final_response=result.final_response,
                )
            elif result.retryable:
                retried = await self._retry_claimed_run(
                    repo=repo,
                    claimed=claimed,
                    reason=result.summary,
                )
                if retried:
                    return WorkerRunResult(
                        "retrying",
                        result.summary,
                        final_response=result.final_response,
                        verification=result.verification,
                        checkpoint=result.checkpoint,
                    )
                await self._finish_failed(
                    repo=repo,
                    task_id=task_id,
                    run_id=run_id,
                    result=result,
                )
            else:
                await self._finish_failed(
                    repo=repo,
                    task_id=task_id,
                    run_id=run_id,
                    result=result,
                )

            await repo.append_event(
                task_id=task_id,
                owner_id=claimed.owner_id,
                run_id=run_id,
                event_type="worker_finished",
                payload={
                    "status": result.status,
                    "summary": result.summary,
                    "verification": result.verification,
                },
            )
            return result
        except Exception as exc:
            logger.exception(
                "Durable task worker failed for %s/%s",
                task_id,
                run_id,
            )
            summary = str(exc) or "Worker failed."
            try:
                current = await repo.get_run(
                    task_id=task_id,
                    run_id=run_id,
                    owner_id=claimed.owner_id,
                )
            except Exception:
                current = None
            if (
                current is not None
                and str(getattr(current, "status", "") or "") in TERMINAL_TASK_STATUSES
            ):
                return WorkerRunResult(str(current.status), summary)
            retried = await self._retry_claimed_run(
                repo=repo,
                claimed=claimed,
                reason=summary,
            )
            if retried:
                return WorkerRunResult("retrying", summary, retryable=True)
            current = await repo.get_run(
                task_id=task_id,
                run_id=run_id,
                owner_id=claimed.owner_id,
            )
            if (
                current is not None
                and current.lease_owner == self.worker_id
                and current.claim_generation == generation
            ):
                await repo.finish_run(
                    task_id=task_id,
                    run_id=run_id,
                    status="failed",
                    summary=summary,
                    error=summary,
                )
                await repo.append_event(
                    task_id=task_id,
                    owner_id=claimed.owner_id,
                    run_id=run_id,
                    event_type="worker_failed",
                    payload={
                        "error": summary,
                        "attempt": int(
                            getattr(claimed, "attempt", 1) or 1
                        ),
                    },
                )
                return WorkerRunResult("failed", summary)
            return WorkerRunResult(
                "skipped",
                "Worker lost its lease; stale-run recovery owns the next attempt.",
            )
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _report_claim_rejection(
        self,
        *,
        repo,
        task_id: str,
        run_id: str,
    ) -> None:
        """Explain a rejected claim; never raise from the diagnostic path.

        When the rejection means the run is orphaned — nobody holds a live lease
        and it is not already terminal — the run is failed and a terminal
        ``worker_failed`` event is appended. Without that the client polls a
        ``queued`` run forever and shows an endless thinking state.
        """
        try:
            task = await repo.get_task(task_id)
            run = (
                await repo.get_run(
                    task_id=task_id,
                    run_id=run_id,
                    owner_id=task.owner_id,
                )
                if task
                else None
            )
        except Exception:
            logger.warning(
                "Durable worker could not claim %s/%s and failed to read its state",
                task_id,
                run_id,
                exc_info=True,
            )
            return

        if run is None:
            logger.warning(
                "Durable worker could not claim %s/%s: run or task missing",
                task_id,
                run_id,
            )
            return

        status = str(getattr(run, "status", "") or "")
        lease_owner = getattr(run, "lease_owner", None)
        lease_expires_at = getattr(run, "lease_expires_at", None)
        cancel_requested = bool(getattr(task, "cancel_requested", False))

        logger.warning(
            "Durable worker could not claim %s/%s: status=%s lease_owner=%s "
            "lease_expires_at=%s claim_generation=%s cancel_requested=%s",
            task_id,
            run_id,
            status or "?",
            lease_owner,
            lease_expires_at,
            getattr(run, "claim_generation", None),
            cancel_requested,
        )

        if status in TERMINAL_TASK_STATUSES or cancel_requested:
            # The run already reached (or is reaching) a terminal state and the
            # owning path emits its own events.
            return
        if lease_owner and lease_is_live(lease_expires_at):
            # Another worker legitimately owns this run.
            return

        reason = (
            "This run could not be started by any worker "
            f"(state: {status or 'unknown'}). Please send the request again."
        )
        try:
            await repo.finish_run(
                task_id=task_id,
                run_id=run_id,
                status="failed",
                summary=reason,
                error=reason,
            )
            await repo.append_event(
                task_id=task_id,
                owner_id=task.owner_id,
                run_id=run_id,
                event_type="worker_failed",
                payload={
                    "worker_id": self.worker_id,
                    "reason": reason,
                    "error_code": "RUN_NOT_CLAIMABLE",
                    "retryable": False,
                },
            )
        except Exception:
            logger.warning(
                "Failed to settle unclaimable durable run %s/%s",
                task_id,
                run_id,
                exc_info=True,
            )

    async def _lease_heartbeat(
        self,
        *,
        repo,
        task_id: str,
        run_id: str,
        claim_generation: int,
    ) -> None:
        interval = max(
            1,
            min(
                int(settings.task_worker_heartbeat_interval_seconds),
                max(1, int(settings.task_worker_lease_seconds) // 2),
            ),
        )
        while True:
            await asyncio.sleep(interval)
            renewed = await repo.renew_lease(
                task_id=task_id,
                run_id=run_id,
                worker_id=self.worker_id,
                claim_generation=claim_generation,
            )
            if not renewed:
                raise RuntimeError("Durable worker lost its lease generation.")

    async def _wait_for_durable_subagents(
        self,
        *,
        repo,
        claimed,
    ) -> bool:
        """Keep the parent lease alive until its durable children settle."""
        db = getattr(repo, "_db", None)
        session_id = str(getattr(claimed, "session_id", "") or "")
        run_id = str(getattr(claimed, "run_id", "") or "")
        owner_id = str(getattr(claimed, "owner_id", "") or "")
        if db is None or not session_id or not run_id or not owner_id:
            return False
        from nexus.subagent_store import FirestoreSubagentRepository

        subagents = FirestoreSubagentRepository(db=db)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(
            1,
            int(settings.subagent_parent_wait_seconds),
        )
        while loop.time() < deadline:
            records = await subagents.list_for_parent(
                parent_session_id=session_id,
                parent_run_id=run_id,
                owner_id=owner_id,
            )
            if records and not any(
                str(record.get("status") or "")
                in {"queued", "running"}
                for record in records
            ):
                return True
            await asyncio.sleep(min(2.0, max(0.1, deadline - loop.time())))
        return False

    async def _retry_claimed_run(self, *, repo, claimed, reason: str) -> bool:
        retried = await repo.requeue_run(
            task_id=str(getattr(claimed, "task_id", "") or ""),
            run_id=str(getattr(claimed, "run_id", "") or ""),
            reason=reason,
            expected_generation=int(
                getattr(claimed, "claim_generation", 0) or 0
            ),
            worker_id=self.worker_id,
        )
        if retried is None:
            return False
        delay = min(
            int(settings.task_worker_retry_base_seconds)
            * (2 ** max(0, retried.attempt - 2)),
            300,
        )
        from nexus.task_queue import task_queue

        enqueue = await task_queue.enqueue_task_run(
            task_id=retried.task_id,
            run_id=retried.run_id,
            claim_token=retried.claim_token,
            delay_seconds=delay,
        )
        await repo.append_event(
            task_id=retried.task_id,
            owner_id=retried.owner_id,
            run_id=retried.run_id,
            event_type="worker_retry_scheduled",
            payload={
                "attempt": retried.attempt,
                "delay_seconds": delay,
                "reason": reason[:1000],
                "queued": enqueue.queued,
                "provider": enqueue.provider,
            },
        )
        return bool(enqueue.queued)

    @staticmethod
    async def _finish_failed(
        *,
        repo,
        task_id: str,
        run_id: str,
        result: WorkerRunResult,
    ) -> None:
        await repo.finish_run(
            task_id=task_id,
            run_id=run_id,
            status="failed",
            summary=result.summary,
            error=result.summary,
            verification=result.verification,
            checkpoint=result.checkpoint,
            final_response=result.final_response,
        )

    async def _execute_claimed_run(
        self,
        *,
        task_id: str,
        run_id: str,
        owner_id: str,
    ) -> WorkerRunResult:
        repo = get_production_task_repository()
        task = await repo.get_task(task_id)
        if not task or task.owner_id != owner_id:
            return WorkerRunResult(
                "failed",
                "Durable task was not found for the claimed owner.",
            )

        run = await repo.get_run(
            task_id=task_id,
            run_id=run_id,
            owner_id=owner_id,
        )
        execution_payload = (
            run.execution_payload if run and run.execution_payload else {}
        )
        metadata = (
            execution_payload.get("metadata")
            if isinstance(execution_payload.get("metadata"), dict)
            else {}
        )
        input_text = str(
            execution_payload.get("input_text") or task.input_text
        ).strip()
        if not input_text:
            return WorkerRunResult(
                "failed",
                "Durable task has no input text to execute.",
            )

        runner = AgentTurnRunner(
            session_manager=get_session_manager(),
            production_task_repository=repo,
        )
        outcome = await runner.run(
            AgentTurnRequest(
                task_id=task_id,
                run_id=run_id,
                owner_id=owner_id,
                session_id=str(
                    execution_payload.get("session_id")
                    or task.session_id
                    or task_id
                ),
                title=task.title,
                input_text=input_text,
                connector_ids=[
                    str(item)
                    for item in execution_payload.get("connector_ids", [])
                    if str(item).strip()
                ],
                tool_ids=[
                    str(item)
                    for item in execution_payload.get("tool_ids", [])
                    if str(item).strip()
                ],
                uploaded_files=[
                    item
                    for item in execution_payload.get("uploaded_files", [])
                    if isinstance(item, dict)
                ],
                emit_user_transcript=not bool(
                    metadata.get("user_transcript_recorded")
                ),
                autonomy_mode=str(
                    execution_payload.get("autonomy_mode")
                    or getattr(task, "autonomy_mode", "")
                    or settings.default_autonomy_mode
                ),
                budget=(
                    execution_payload.get("budget")
                    if isinstance(execution_payload.get("budget"), dict)
                    else getattr(task, "budget", None) or {}
                ),
                checkpoint=(
                    getattr(run, "checkpoint", None)
                    if run
                    else {}
                )
                or {},
            )
        )
        return WorkerRunResult(
            outcome.status,
            outcome.summary,
            final_response=str(getattr(outcome, "final_response", "") or ""),
            verification=dict(getattr(outcome, "verification", {}) or {}),
            checkpoint=dict(getattr(outcome, "checkpoint", {}) or {}),
            retryable=bool(getattr(outcome, "retryable", False)),
        )


task_worker = TaskWorker()
