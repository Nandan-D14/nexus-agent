# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable task worker runtime."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

from nexus.dependencies import get_production_task_repository

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
            await repo.finish_run(
                task_id=task_id,
                run_id=run_id,
                status="completed" if result.status == "completed" else "failed",
                summary=result.summary,
                error=None if result.status == "completed" else result.summary,
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
        """Placeholder execution hook for the next migration slice.

        Keeping this explicit prevents fake success: durable queueing and leases
        are real, but WebSocket-to-worker agent turn migration is a separate
        refactor because it changes live streaming semantics.
        """
        return WorkerRunResult(
            "failed",
            "Durable worker claimed the run, but agent-turn execution has not been migrated yet.",
        )


task_worker = TaskWorker()
