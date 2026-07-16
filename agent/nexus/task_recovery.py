# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Lease-expiry recovery for durable task runs."""

from __future__ import annotations

import asyncio
import logging

from nexus.config import settings


logger = logging.getLogger(__name__)


class StaleRunSweeper:
    def __init__(self, repository, queue) -> None:
        self.repository = repository
        self.queue = queue
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, interval_seconds: int | None = None) -> None:
        if self._running or not settings.task_worker_enabled:
            return
        self._running = True
        interval = max(
            5,
            int(
                interval_seconds
                or settings.stale_run_sweep_interval_seconds
            ),
        )
        self._task = asyncio.create_task(
            self._loop(interval),
            name="durable-stale-run-sweeper",
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _loop(self, interval_seconds: int) -> None:
        while self._running:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Stale durable-run sweep failed")
            await asyncio.sleep(interval_seconds)

    async def sweep(self) -> int:
        recovered = 0
        for run in await self.repository.list_stale_runs(limit=100):
            if run.attempt >= max(1, settings.task_worker_max_attempts):
                summary = (
                    f"Durable run lease expired after {run.attempt} attempts."
                )
                failed = await self.repository.fail_stale_run(
                    task_id=run.task_id,
                    run_id=run.run_id,
                    expected_generation=run.claim_generation,
                    summary=summary,
                )
                if failed:
                    await self.repository.append_event(
                        task_id=run.task_id,
                        owner_id=run.owner_id,
                        run_id=run.run_id,
                        event_type="worker_recovery_exhausted",
                        payload={
                            "attempt": run.attempt,
                            "claim_generation": run.claim_generation,
                            "summary": summary,
                        },
                    )
                    recovered += 1
                continue

            requeued = await self.repository.requeue_run(
                task_id=run.task_id,
                run_id=run.run_id,
                reason="Worker lease expired; recovering from checkpoint.",
                expected_generation=run.claim_generation,
            )
            if requeued is None:
                continue
            delay = min(
                int(settings.task_worker_retry_base_seconds)
                * (2 ** max(0, requeued.attempt - 2)),
                300,
            )
            enqueue = await self.queue.enqueue_task_run(
                task_id=requeued.task_id,
                run_id=requeued.run_id,
                claim_token=requeued.claim_token,
                delay_seconds=delay,
            )
            await self.repository.append_event(
                task_id=requeued.task_id,
                owner_id=requeued.owner_id,
                run_id=requeued.run_id,
                event_type="worker_recovered",
                payload={
                    "attempt": requeued.attempt,
                    "claim_generation": requeued.claim_generation,
                    "delay_seconds": delay,
                    "queued": enqueue.queued,
                    "provider": enqueue.provider,
                },
            )
            if not enqueue.queued:
                await self.repository.finish_run(
                    task_id=requeued.task_id,
                    run_id=requeued.run_id,
                    status="failed",
                    summary="Crash recovery could not enqueue the next attempt.",
                    error=enqueue.reason,
                    checkpoint=requeued.checkpoint or {},
                )
            recovered += 1
        return recovered


__all__ = ["StaleRunSweeper"]
