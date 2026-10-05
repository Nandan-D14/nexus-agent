# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Background Task Manager — handles long-running tasks with user permission."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTask:
    """Represents a single background task."""

    task_id: str
    description: str
    estimated_seconds: int
    agent: str = "nexus"
    approved: bool = False
    permission_step_id: str | None = None
    background_step_id: str | None = None
    _permission_future: asyncio.Future | None = field(default=None, repr=False)
    _asyncio_task: asyncio.Task | None = field(default=None, repr=False)


class BackgroundTaskManager:
    """Manages background tasks that require user permission before execution."""

    def __init__(self, send_json: Callable[..., Any]) -> None:
        self._send_json = send_json
        self._tasks: dict[str, BackgroundTask] = {}
        self._on_permission_requested: Callable[[BackgroundTask], Awaitable[str | None]] | None = None
        self._on_permission_resolved: Callable[[BackgroundTask, bool], Awaitable[None]] | None = None
        self._on_task_started: Callable[[BackgroundTask], Awaitable[str | None]] | None = None
        self._on_task_finished: Callable[[BackgroundTask, bool, str], Awaitable[None]] | None = None

    def set_callbacks(
        self,
        *,
        on_permission_requested: Callable[[BackgroundTask], Awaitable[str | None]] | None = None,
        on_permission_resolved: Callable[[BackgroundTask, bool], Awaitable[None]] | None = None,
        on_task_started: Callable[[BackgroundTask], Awaitable[str | None]] | None = None,
        on_task_finished: Callable[[BackgroundTask, bool, str], Awaitable[None]] | None = None,
    ) -> None:
        self._on_permission_requested = on_permission_requested
        self._on_permission_resolved = on_permission_resolved
        self._on_task_started = on_task_started
        self._on_task_finished = on_task_finished

    async def request_permission(
        self,
        description: str,
        estimated_seconds: int,
        agent: str = "nexus",
    ) -> tuple[str, bool]:
        """Send a permission request to the frontend and wait for user response.

        Returns:
            Tuple of (task_id, approved).
        """
        task_id = uuid.uuid4().hex[:8]
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()

        task = BackgroundTask(
            task_id=task_id,
            description=description,
            estimated_seconds=estimated_seconds,
            agent=agent,
        )
        task._permission_future = future
        self._tasks[task_id] = task

        if self._on_permission_requested:
            try:
                task.permission_step_id = await self._on_permission_requested(task)
            except Exception:
                logger.exception("Failed to create permission step for task %s", task_id)

        await self._send_json({
            "type": "permission_request",
            "task_id": task_id,
            "description": description,
            "estimated_seconds": estimated_seconds,
            "agent": agent,
        })
        logger.info("approval_requested task=%s agent=%s", task_id, agent)

        try:
            approved = await asyncio.wait_for(future, timeout=120.0)
        except asyncio.TimeoutError:
            approved = False
            logger.warning("Permission request %s timed out", task_id)
            await self._send_json({
                "type": "bg_task_complete",
                "task_id": task_id,
                "success": False,
                "result": "Permission request timed out — user did not respond.",
            })

        task.approved = approved
        task._permission_future = None
        if not approved:
            # Denied/timed-out requests never run; drop them so the registry
            # does not grow for the lifetime of the orchestrator.
            self._tasks.pop(task_id, None)
        logger.info("approval_resolved task=%s approved=%s", task_id, approved)
        if self._on_permission_resolved:
            try:
                await self._on_permission_resolved(task, approved)
            except Exception:
                logger.exception("Failed to resolve permission step for task %s", task_id)
        return task_id, approved

    def handle_permission_response(self, task_id: str, approved: bool) -> None:
        """Resolve the pending permission future when user responds."""
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("Unknown task_id for permission response: %s", task_id)
            return
        if task._permission_future and not task._permission_future.done():
            task._permission_future.set_result(approved)

    async def send_progress(self, task_id: str, progress: int, message: str) -> None:
        """Send a progress update to the frontend."""
        await self._send_json({
            "type": "bg_task_progress",
            "task_id": task_id,
            "progress": min(100, max(0, progress)),
            "message": message,
        })

    async def send_complete(
        self, task_id: str, success: bool, result: str
    ) -> None:
        """Send a completion event to the frontend."""
        await self._send_json({
            "type": "bg_task_complete",
            "task_id": task_id,
            "success": success,
            "result": result[:500] if result else "",
        })

    def get_task(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)
