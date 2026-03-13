"""Background Task Manager — handles long-running tasks with user permission."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTask:
    """Represents a single background task."""

    task_id: str
    description: str
    estimated_seconds: int
    agent: str = "nexus"
    approved: bool = False
    _permission_future: asyncio.Future | None = field(default=None, repr=False)
    _asyncio_task: asyncio.Task | None = field(default=None, repr=False)


class BackgroundTaskManager:
    """Manages background tasks that require user permission before execution."""

    def __init__(self, send_json: Callable[..., Any]) -> None:
        self._send_json = send_json
        self._tasks: dict[str, BackgroundTask] = {}

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

        await self._send_json({
            "type": "permission_request",
            "task_id": task_id,
            "description": description,
            "estimated_seconds": estimated_seconds,
            "agent": agent,
        })

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

    async def run_task(
        self,
        task_id: str,
        coro: Coroutine,
    ) -> Any:
        """Run a coroutine as a tracked background task.

        Sends progress/complete events automatically. The coroutine should
        be awaitable and return a result string or None.
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("run_task called with unknown task_id: %s", task_id)
            return None

        async def _wrapper() -> Any:
            try:
                result = await coro
                await self.send_complete(task_id, success=True, result=str(result) if result else "Task completed.")
                return result
            except asyncio.CancelledError:
                await self.send_complete(task_id, success=False, result="Task was cancelled.")
                return None
            except Exception as exc:
                logger.exception("Background task %s failed", task_id)
                await self.send_complete(task_id, success=False, result=f"Task failed: {exc}")
                return None

        asyncio_task = asyncio.create_task(_wrapper())
        task._asyncio_task = asyncio_task
        return await asyncio_task

    def get_task(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)
