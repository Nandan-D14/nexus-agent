"""Background task permission tool — agent requests user approval for long tasks."""

from __future__ import annotations

import logging

from nexus.tools._context import get_bg_task_manager

logger = logging.getLogger(__name__)


async def request_background_task(
    description: str, estimated_seconds: int = 60
) -> dict:
    """Request user permission to run a long-running task in the background.

    Use this when a task may take more than 30 seconds — e.g., installing
    packages, running a full test suite, large downloads, or long builds.
    The user will see a permission card in the chat and can approve or deny.

    Args:
        description: Clear, short description of what the task will do.
                     Example: "Install Node.js dependencies and run the test suite"
        estimated_seconds: Rough estimate of how long the task will take (in seconds).

    Returns:
        dict with task_id, approved status, and message.
    """
    try:
        manager = get_bg_task_manager()
    except RuntimeError:
        return {
            "task_id": "",
            "approved": False,
            "message": "Background task manager is not available in this session.",
        }

    if manager is None:
        return {
            "task_id": "",
            "approved": False,
            "message": "Background task manager is not initialized.",
        }

    task_id, approved = await manager.request_permission(
        description=description,
        estimated_seconds=estimated_seconds,
    )

    return {
        "task_id": task_id,
        "approved": approved,
        "message": (
            f"User approved background task {task_id}."
            if approved
            else "User denied the background task request."
        ),
    }
