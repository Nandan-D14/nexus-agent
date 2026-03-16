"""Browser tool for opening URLs."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def open_browser(url: str) -> dict:
    """Open a URL in the web browser (Firefox).

    After calling this, take_screenshot() to see the loaded page.

    Args:
        url: The full URL to navigate to (include https://).

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.open_url(url)
        # Reset screenshot cooldown so agent can screenshot right after
        from nexus.tools.screen import _last_call_time
        _last_call_time.t = 0.0
        return {"status": "success", "message": f"Opened {url} in browser. Take a screenshot to see the page."}
    except Exception as e:
        logger.error("open_browser failed: %s", e)
        return {"status": "error", "message": f"Failed to open browser: {e}"}
