# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""UI control tools for agent to interact with the frontend interface."""

from __future__ import annotations

import asyncio
import logging

from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


@normalized_tool
def show_desktop_panel(reason: str = "") -> dict:
    """Switch the frontend view to the Desktop panel to show the user what's happening on screen.

    Use this tool when you need to:
    - Show the user something visually on the desktop
    - Open a browser and demonstrate something
    - Display a file or document you've created
    - Perform GUI actions that the user should see
    - Take the user to see the terminal output directly

    Args:
        reason: Brief explanation of why you're switching to desktop view.
                Example: "Opening browser to show you the search results"

    Returns:
        NormalizedToolResult confirming the UI switch was requested.
    """
    try:
        from nexus.tools._context import get_send_json

        send_json = get_send_json()
        reason_text = reason.strip() or "Showing desktop view"

        if send_json:
            asyncio.create_task(
                send_json({
                    "type": "ui_action",
                    "action": "switch_tab",
                    "target": "desktop",
                    "reason": reason_text,
                })
            )
            logger.info("UI action sent: switch to desktop - %s", reason_text)
        else:
            logger.warning("send_json not available - cannot send UI action")

        return tool_success(
            f"Switched to desktop panel: {reason_text}",
            target="desktop", reason=reason_text,
        )

    except Exception as e:
        logger.error("show_desktop_panel failed: %s", e)
        return tool_error(f"Failed to switch to desktop panel: {e}")


@normalized_tool
def show_workflow_panel(reason: str = "") -> dict:
    """Switch the frontend view back to the Workflow panel showing the step chain.

    Use this tool when you want to return the user to the workflow view after
    showing something on the desktop, or when the visual demonstration is complete.

    Args:
        reason: Brief explanation of why you're switching back.
                Example: "Returning to workflow view to continue the task"

    Returns:
        NormalizedToolResult confirming the UI switch was requested.
    """
    try:
        from nexus.tools._context import get_send_json

        send_json = get_send_json()
        reason_text = reason.strip() or "Returning to workflow view"

        if send_json:
            asyncio.create_task(
                send_json({
                    "type": "ui_action",
                    "action": "switch_tab",
                    "target": "workflow",
                    "reason": reason_text,
                })
            )
            logger.info("UI action sent: switch to workflow - %s", reason_text)
        else:
            logger.warning("send_json not available - cannot send UI action")

        return tool_success(
            f"Switched to workflow panel: {reason_text}",
            target="workflow", reason=reason_text,
        )

    except Exception as e:
        logger.error("show_workflow_panel failed: %s", e)
        return tool_error(f"Failed to switch to workflow panel: {e}")
