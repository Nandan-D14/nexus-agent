# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable task worker runtime."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

from nexus.agent_turn_runner import AgentTurnRequest, AgentTurnRunner
from nexus.dependencies import get_production_task_repository, get_session_manager

logger = logging.getLogger(__name__)


@dataclass
class WorkerRunResult:
    status: str
    summary: str


class TaskWorker:
    """Durable production worker for claimed task runs.

    The worker owns the claim/lease lifecycle and delegates the actual agent
    turn to ``AgentTurnRunner`` so live and durable execution share one path.
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
        """Run a claimed durable task through the shared agent turn runner."""
        repo = get_production_task_repository()
        task = await repo.get_task(task_id)
        if not task or task.owner_id != owner_id:
            return WorkerRunResult("failed", "Durable task was not found for the claimed owner.")

        run = await repo.get_run(task_id=task_id, run_id=run_id, owner_id=owner_id)
        execution_payload = run.execution_payload if run and run.execution_payload else {}
        metadata = execution_payload.get("metadata") if isinstance(execution_payload.get("metadata"), dict) else {}
        input_text = str(execution_payload.get("input_text") or task.input_text).strip()
        if not input_text:
            return WorkerRunResult("failed", "Durable task has no input text to execute.")

        session_manager = get_session_manager()
        runner = AgentTurnRunner(
            session_manager=session_manager,
            production_task_repository=repo,
        )
        outcome = await runner.run(
            AgentTurnRequest(
                task_id=task_id,
                run_id=run_id,
                owner_id=owner_id,
                session_id=str(execution_payload.get("session_id") or task.session_id or task_id),
                title=task.title,
                input_text=input_text,
                connector_ids=[
                    str(item)
                    for item in execution_payload.get("connector_ids", [])
                    if str(item).strip()
                ],
                uploaded_files=[
                    item
                    for item in execution_payload.get("uploaded_files", [])
                    if isinstance(item, dict)
                ],
                emit_user_transcript=not bool(metadata.get("user_transcript_recorded")),
            )
        )
        return WorkerRunResult(outcome.status, outcome.summary)


task_worker = TaskWorker()
