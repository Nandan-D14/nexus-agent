# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""In-process ticker that fires due schedules in non-production."""

from __future__ import annotations

import asyncio
import logging

from nexus.config import settings

logger = logging.getLogger(__name__)


class ScheduleTicker:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, interval_seconds: int | None = None) -> None:
        if self._running or settings.is_production:
            return
        if not settings.task_worker_enabled:
            return
        self._running = True
        interval = max(5, int(interval_seconds or settings.schedule_tick_interval_seconds))
        self._task = asyncio.create_task(self._loop(interval), name="schedule-ticker")

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
                from nexus.schedule_dispatch import tick_due_schedules

                result = await tick_due_schedules()
                if result.get("fired") or result.get("errors"):
                    logger.info(
                        "Schedule ticker fired=%s skipped=%s errors=%s",
                        result.get("fired"),
                        result.get("skipped"),
                        result.get("errors"),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Schedule ticker failed")
            await asyncio.sleep(interval_seconds)
