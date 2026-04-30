"""UI control tools for agent to interact with the frontend interface."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def show_desktop_panel(reason: str = "") -> dict[str, Any]:
    """Switch the frontend view to the Desktop panel to show the user what's happening on screen.

    Use this tool when you need to:
    - Show the user something visually on the desktop
    - Open a browser and demonstrate something
    - Display a file or document you've created
    - Perform GUI actions that the user should see
    - Take the user to see the terminal output directly

    The tool sends a UI action message to the frontend to switch from the Workflow
    view to the Desktop view, allowing the user to see the live VNC stream.

    Args:
        reason: Brief explanation of why you're switching to desktop view.
                Example: "Opening browser to show you the search results"

    Returns:
        dict confirming the UI action was requested.

    Example:
        >>> show_desktop_panel("Opening LibreOffice to show you the generated document")
        {"status": "requested", "action": "switch_tab", "target": "desktop", "reason": "Opening LibreOffice..."}
    """
    import asyncio
    try:
        from nexus.tools._context import get_send_json

        send_json = get_send_json()
        reason_text = reason.strip() or "Showing desktop view"

        if send_json:
            # Fire and forget - don't block the agent
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

        return {
            "status": "requested",
            "action": "switch_tab",
            "target": "desktop",
            "reason": reason_text,
        }

    except Exception as e:
        logger.error("show_desktop_panel failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
        }


def show_workflow_panel(reason: str = "") -> dict[str, Any]:
    """Switch the frontend view back to the Workflow panel showing the step chain.

    Use this tool when you want to return the user to the workflow view after
    showing something on the desktop, or when the visual demonstration is complete.

    Args:
        reason: Brief explanation of why you're switching back.
                Example: "Returning to workflow view to continue the task"

    Returns:
        dict confirming the UI action was requested.
    """
    import asyncio
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

        return {
            "status": "requested",
            "action": "switch_tab",
            "target": "workflow",
            "reason": reason_text,
        }

    except Exception as e:
        logger.error("show_workflow_panel failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
        }
