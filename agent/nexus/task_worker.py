# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable task worker runtime."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

from starlette.websockets import WebSocketState

from nexus.dependencies import get_production_task_repository, get_session_manager
from nexus.orchestrator import NexusOrchestrator
from nexus.production_tasks import map_history_status_to_durable
from nexus.runtime_config import resolve_session_runtime_config

logger = logging.getLogger(__name__)


@dataclass
class WorkerRunResult:
    status: str
    summary: str


class TaskWorker:
    """Initial production worker.

    This slice establishes durable claim/lease/event behavior. The full agent
    turn migration can plug into ``_execute_claimed_run`` without changing the
    Cloud Tasks and Firestore contract.
    """

    def __init__(self, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"{socket.gethostname()}-worker"

    async def run_once(self, *, task_id: str, run_id: str) -> WorkerRunResult:
        repo = get_production_task_repository()
        claimed = await repo.claim_run(task_id=task_id, run_id=run_id, worker_id=self.worker_id)
        if not claimed:
            return WorkerRunResult("skipped", "Run is already leased, cancelled, missing, or complete.")

        await repo.append_event(
            task_id=task_id,
            owner_id=claimed.owner_id,
            run_id=run_id,
            event_type="worker_claimed",
            payload={"worker_id": self.worker_id},
        )

        try:
            result = await self._execute_claimed_run(task_id=task_id, run_id=run_id, owner_id=claimed.owner_id)
            finish_status = (
                "completed"
                if result.status == "completed"
                else "cancelled"
                if result.status == "cancelled"
                else "failed"
            )
            await repo.finish_run(
                task_id=task_id,
                run_id=run_id,
                status=finish_status,
                summary=result.summary,
                error=None if finish_status == "completed" else result.summary,
            )
            await repo.append_event(
                task_id=task_id,
                owner_id=claimed.owner_id,
                run_id=run_id,
                event_type="worker_finished",
                payload={"status": result.status, "summary": result.summary},
            )
            return result
        except Exception as exc:
            logger.exception("Durable task worker failed for %s/%s", task_id, run_id)
            summary = str(exc) or "Worker failed."
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
                payload={"error": summary},
            )
            return WorkerRunResult("failed", summary)

    async def _execute_claimed_run(self, *, task_id: str, run_id: str, owner_id: str) -> WorkerRunResult:
        """Run a claimed durable task through the existing agent turn path."""
        repo = get_production_task_repository()
        task = await repo.get_task(task_id)
        if not task or task.owner_id != owner_id:
            return WorkerRunResult("failed", "Durable task was not found for the claimed owner.")

        input_text = task.input_text.strip()
        if not input_text:
            return WorkerRunResult("failed", "Durable task has no input text to execute.")

        session_manager = get_session_manager()
        history_repository = session_manager.history_repository
        user_settings = {}
        if history_repository:
            try:
                user_settings = await history_repository.get_user_settings(owner_id)
            except Exception:
                logger.warning("Failed to load user settings for durable task %s", task_id, exc_info=True)
        runtime_config = resolve_session_runtime_config(user_settings)

        session_id = task.session_id or task_id
        session = await session_manager.get_session(session_id)
        if not session or session.owner_id != owner_id or getattr(session, "runtime_config", None) is None:
            session = await session_manager.create_session(
                owner_id=owner_id,
                runtime_config=runtime_config,
                session_id=session_id,
                task_id=task_id,
                initial_title=task.title,
            )

        session.task_id = task_id
        session.current_run_id = run_id
        session.run_status = "queued"

        async def activate_sandbox() -> None:
            await session_manager.activate_session(session.id)

        orchestrator = NexusOrchestrator(
            session=session,
            ws=_WorkerEventWebSocket(),
            history_repository=history_repository,
            production_task_repository=repo,
            ensure_sandbox_ready=activate_sandbox,
        )
        try:
            await orchestrator.initialize(lazy_sandbox=True)
            await orchestrator.handle_text_input(input_text)
            durable_status = map_history_status_to_durable(session.run_status)
            if durable_status in {"failed", "cancelled"}:
                return WorkerRunResult(durable_status, f"Agent turn {durable_status}.")
            return WorkerRunResult("completed", "Agent turn completed.")
        finally:
            await orchestrator.close()


class _WorkerEventWebSocket:
    """No-op WebSocket facade used by durable workers.

    The orchestrator still expects a WebSocket-like object for its existing
    locked send path. Durable replay comes from ``DurableEventSink``; this
    facade only keeps the old live transport dependency inert.
    """

    client_state = WebSocketState.CONNECTED
    application_state = WebSocketState.CONNECTED

    async def send_json(self, data: dict) -> None:
        return None

    async def send_bytes(self, data: bytes) -> None:
        return None


task_worker = TaskWorker()
