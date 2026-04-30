"""Browser tool for opening URLs."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def open_browser(url: str) -> dict:
    """Open a URL in the web browser (Firefox).

    After calling this, wait for the page to settle and take_screenshot()
    only if visible browser state is needed.

    Args:
        url: The full URL to navigate to (include https://).

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.open_url(url)
        from nexus.tools.screen import mark_screen_changed
        mark_screen_changed("open_browser")
        return {"status": "success", "message": f"Opened {url} in browser. Wait briefly before observing if visual state is needed."}
    except Exception as e:
        logger.error("open_browser failed: %s", e)
        return {"status": "error", "message": f"Failed to open browser: {e}"}
