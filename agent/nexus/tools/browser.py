# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Browser tool for opening URLs."""

from __future__ import annotations

import logging

from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


@normalized_tool
def open_browser(url: str) -> dict:
    """Open a URL in the web browser (Firefox).

    After calling this, wait for the page to settle and take_screenshot()
    only if visible browser state is needed.

    Args:
        url: The full URL to navigate to (include https://).

    Returns:
        NormalizedToolResult confirming navigation.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.open_url(url)
        from nexus.tools.screen import mark_screen_changed
        mark_screen_changed("open_browser")
        return tool_success(
            f"Opened {url} in browser",
            url=url, action="open_browser",
        )
    except Exception as e:
        logger.error("open_browser failed: %s", e)
        return tool_error(
            f"Failed to open {url} in browser: {e}",
            suggested_alternatives=["web_search", "scrape_web_page"],
        )
