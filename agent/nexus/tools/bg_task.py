# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Background task permission tool — agent requests user approval for long tasks."""

from __future__ import annotations

import logging

from nexus.tools._context import get_bg_task_manager
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


@normalized_tool
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
        NormalizedToolResult with task_id and approval status.
    """
    try:
        manager = get_bg_task_manager()
    except RuntimeError:
        return tool_error(
            "Background task manager is not available in this session.",
            error_code="TOOL_UNAVAILABLE",
        )

    if manager is None:
        return tool_error(
            "Background task manager is not initialized.",
            error_code="TOOL_UNAVAILABLE",
        )

    task_id, approved = await manager.request_permission(
        description=description,
        estimated_seconds=estimated_seconds,
    )

    if approved:
        return tool_success(
            f"User approved background task {task_id}",
            task_id=task_id, approved=True,
            estimated_seconds=estimated_seconds,
        )
    return tool_error(
        "User denied the background task request.",
        error_code="USER_DENIED",
        task_id=task_id,
    )
