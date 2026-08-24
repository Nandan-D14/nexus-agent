# Proprietary and non-commercial use only.

"""Collaborators extracted from the SubagentSupervisor god object.

- :class:`SubagentStoreCodec` — pure (de)serialization between stored dicts and
  :class:`SubagentRecord` instances. Self-contained (operates on its arguments).
- :class:`SubagentEventEmitter` — emits history steps and frontend events for a
  subagent's lifecycle. Bound to the owning supervisor so it can read
  ``history_repository`` / ``subagent_repository`` / ``send_json``.

The :class:`~nexus.subagents.SubagentSupervisor` composes both and delegates to
them via ``__getattr__``, so its own methods keep calling ``self._storage_payload``,
``self._mark_started`` etc. unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from nexus.subagents import SubagentRecord

if TYPE_CHECKING:
    from nexus.subagents import SubagentSupervisor


class SubagentStoreCodec:
    """(De)serialize SubagentRecord <-> stored Firestore dict."""

    def _storage_payload(self, record: SubagentRecord) -> dict[str, Any]:
        return {
            "subagentId": record.subagent_id,
            "hiddenSessionId": record.hidden_session_id,
            "parentSessionId": record.parent_session_id,
            "parentRunId": record.parent_run_id,
            "parentTaskId": record.parent_task_id,
            "ownerId": record.owner_id,
            "role": record.role,
            "typeName": record.type_name,
            "prompt": record.prompt[:8_000],
            "stepId": record.step_id,
        }

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        return value if isinstance(value, datetime) else None

    def _record_from_storage(
        self,
        stored: dict[str, Any],
    ) -> SubagentRecord:
        return SubagentRecord(
            subagent_id=str(stored.get("subagentId") or ""),
            hidden_session_id=str(stored.get("hiddenSessionId") or ""),
            parent_session_id=str(stored.get("parentSessionId") or ""),
            parent_run_id=(
                stored.get("parentRunId")
                if isinstance(stored.get("parentRunId"), str)
                else None
            ),
            parent_task_id=(
                stored.get("parentTaskId")
                if isinstance(stored.get("parentTaskId"), str)
                else None
            ),
            owner_id=str(stored.get("ownerId") or ""),
            role=str(stored.get("role") or "worker"),
            type_name=str(stored.get("typeName") or "writer"),
            prompt=str(stored.get("prompt") or ""),
            status=str(stored.get("status") or "queued"),
            result=(
                stored.get("result")
                if isinstance(stored.get("result"), str)
                else None
            ),
            error=(
                stored.get("error")
                if isinstance(stored.get("error"), str)
                else None
            ),
            step_id=(
                stored.get("stepId")
                if isinstance(stored.get("stepId"), str)
                else None
            ),
            terminal_recorded=bool(stored.get("terminalRecorded")),
            result_consumed=bool(stored.get("resultConsumed")),
            claim_generation=int(
                stored.get("claimGeneration", 0) or 0
            ),
            lease_owner=(
                stored.get("leaseOwner")
                if isinstance(stored.get("leaseOwner"), str)
                else None
            ),
            lease_expires_at=self._coerce_datetime(
                stored.get("leaseExpiresAt")
            ),
            checkpoint=(
                dict(stored.get("checkpoint") or {})
                if isinstance(stored.get("checkpoint"), dict)
                else {}
            ),
            created_at=self._coerce_datetime(stored.get("createdAt"))
            or datetime.now(timezone.utc),
            updated_at=self._coerce_datetime(stored.get("updatedAt"))
            or datetime.now(timezone.utc),
        )

    def _apply_storage_record(
        self,
        record: SubagentRecord,
        stored: dict[str, Any],
    ) -> None:
        loaded = self._record_from_storage(stored)
        for field_name in (
            "hidden_session_id",
            "parent_session_id",
            "parent_run_id",
            "parent_task_id",
            "owner_id",
            "role",
            "type_name",
            "prompt",
            "status",
            "result",
            "error",
            "step_id",
            "terminal_recorded",
            "result_consumed",
            "claim_generation",
            "lease_owner",
            "lease_expires_at",
            "checkpoint",
            "created_at",
            "updated_at",
        ):
            setattr(record, field_name, getattr(loaded, field_name))

    @staticmethod
    def _canonical_type(type_name: str) -> str:
        lowered = str(type_name or "").strip().lower()
        if any(part in lowered for part in ("research", "browser", "web", "search")):
            return "researcher"
        if any(part in lowered for part in ("code", "terminal", "shell")):
            return "coder"
        if any(part in lowered for part in ("writer", "general", "document")):
            return "writer"
        raise ValueError(
            "Subagent type must be researcher, coder, or writer."
        )


class SubagentEventEmitter:
    """Emit lifecycle history steps and frontend events for a subagent.

    Bound to the owning supervisor; reads ``history_repository`` /
    ``subagent_repository`` / ``send_json`` from it via ``__getattr__``.
    """

    def __init__(self, owner: "SubagentSupervisor") -> None:
        self._owner = owner

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        owner = self.__dict__.get("_owner")
        if owner is None:
            raise AttributeError(name)
        return getattr(owner, name)

    async def _mark_started(self, record: SubagentRecord) -> None:
        metadata = self._metadata(record)
        if self.history_repository and record.parent_run_id:
            step = await self.history_repository.create_step(
                session_id=record.parent_session_id,
                run_id=record.parent_run_id,
                step_type="subagent_started",
                title=f"{record.role} started",
                detail=record.prompt[:1500],
                status="running",
                source="subagent_supervisor",
                external_ref=record.subagent_id,
                metadata=metadata,
            )
            record.step_id = step.step_id
            if self.subagent_repository is not None:
                await self.subagent_repository.update_record(
                    subagent_id=record.subagent_id,
                    owner_id=record.owner_id,
                    updates={
                        "stepId": record.step_id,
                        "status": record.status,
                    },
                )
            await self._emit({"type": "step_started", "step": self._step_payload(step)})
        elif self.subagent_repository is not None:
            await self.subagent_repository.update_record(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
                updates={"status": record.status},
            )
        await self._emit({"type": "subagent_started", **metadata})

    async def _record_progress(self, record: SubagentRecord, detail: str) -> None:
        metadata = self._metadata(record)
        if self.history_repository and record.parent_run_id:
            step = await self.history_repository.create_step(
                session_id=record.parent_session_id,
                run_id=record.parent_run_id,
                step_type="subagent_progress",
                title=f"{record.role} progress",
                detail=detail[:1500],
                status="completed",
                source="subagent_supervisor",
                external_ref=record.subagent_id,
                metadata=metadata,
            )
            await self._emit({"type": "step_completed", "step": self._step_payload(step)})
        await self._emit({"type": "subagent_progress", "detail": detail, **metadata})

    async def _mark_completed(self, record: SubagentRecord) -> None:
        if record.terminal_recorded:
            return
        metadata = self._metadata(record)
        detail = record.result or "Subagent completed."
        if self.history_repository and record.parent_run_id and record.step_id:
            step = await self.history_repository.complete_step(
                session_id=record.parent_session_id,
                run_id=record.parent_run_id,
                step_id=record.step_id,
                detail=detail[:1500],
                metadata={**metadata, "result": detail[:4000]},
            )
            if step is not None:
                await self._emit({"type": "step_completed", "step": self._step_payload(step)})
        record.terminal_recorded = True
        if self.subagent_repository is not None:
            await self.subagent_repository.update_record(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
                updates={"terminalRecorded": True},
            )
        await self._emit({"type": "subagent_completed", "result": detail, **metadata})

    async def _mark_failed(self, record: SubagentRecord, *, status: str = "failed") -> None:
        if record.terminal_recorded:
            return
        metadata = self._metadata(record)
        detail = record.error or "Subagent failed."
        if self.history_repository and record.parent_run_id and record.step_id:
            step = await self.history_repository.fail_step(
                session_id=record.parent_session_id,
                run_id=record.parent_run_id,
                step_id=record.step_id,
                detail=detail[:1500],
                error=detail[:1500],
                status=status,
                metadata=metadata,
            )
            if step is not None:
                await self._emit({"type": "step_failed", "step": self._step_payload(step)})
        record.terminal_recorded = True
        if self.subagent_repository is not None:
            await self.subagent_repository.update_record(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
                updates={"terminalRecorded": True},
            )
        await self._emit({"type": "subagent_failed", "error": detail, **metadata})

    async def _emit(self, payload: dict[str, Any]) -> None:
        if self.send_json is None:
            return
        await self.send_json(payload)

    def _metadata(self, record: SubagentRecord) -> dict[str, Any]:
        return {
            "subagent_id": record.subagent_id,
            "hidden_session_id": record.hidden_session_id,
            "role": record.role,
            "type_name": record.type_name,
            "parent_session_id": record.parent_session_id,
            "parent_run_id": record.parent_run_id,
            "parent_task_id": record.parent_task_id,
            "status": record.status,
            "claim_generation": record.claim_generation,
        }

    def _step_payload(self, step: Any) -> dict[str, Any]:
        return {
            "step_id": step.step_id,
            "run_id": step.run_id,
            "session_id": step.session_id,
            "task_id": getattr(step, "task_id", None),
            "step_type": step.step_type,
            "status": step.status,
            "title": step.title,
            "detail": step.detail,
            "created_at": step.created_at.isoformat() if step.created_at else None,
            "updated_at": step.updated_at.isoformat() if step.updated_at else None,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            "step_index": step.step_index,
            "source": step.source,
            "error": step.error,
            "external_ref": step.external_ref,
            "metadata": step.metadata or {},
        }
