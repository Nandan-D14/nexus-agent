# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Typed Playwright browser tools using the provisioned Chromium CDP target."""

from __future__ import annotations

import json
import logging
from typing import Any

from nexus.config import settings
from nexus.tools._context import get_sandbox
from nexus.tools.base import normalized_tool, tool_error, tool_success


logger = logging.getLogger(__name__)


def _mark_browser_mutation(action: str) -> None:
    from nexus.tools.screen import mark_screen_changed
    from nexus.tools.screen_state import mark_dirty

    mark_screen_changed(action)
    mark_dirty(action)


def _mark_browser_observed() -> None:
    from nexus.tools.screen_state import clear_dirty

    clear_dirty()


def _execute_playwright_script(script_body: str) -> dict[str, Any]:
    sandbox = get_sandbox()
    try:
        cdp = sandbox.ensure_chromium_cdp()
    except Exception as exc:
        return {
            "ok": False,
            "data": {},
            "error": str(exc) or "Chromium CDP is unavailable",
            "error_code": "CDP_UNAVAILABLE",
            "retry_hint": "Restart or reconnect the sandbox browser.",
        }

    port = int(cdp.get("port") or settings.browser_cdp_port)
    full_script = f"""
import json
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    print(json.dumps({{"ok": False, "data": {{}}, "error": "Playwright unavailable: " + str(exc), "error_code": "PLAYWRIGHT_UNAVAILABLE", "retry_hint": "Re-provision Chromium."}}))
    raise SystemExit(0)

def main():
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:{port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
{script_body}
            print(json.dumps({{"ok": True, "data": data, "error": None, "error_code": "", "retry_hint": None}}))
    except Exception as exc:
        print(json.dumps({{"ok": False, "data": {{}}, "error": str(exc), "error_code": type(exc).__name__.upper(), "retry_hint": "Inspect the current DOM, selector, URL, and CDP state before retrying."}}))

if __name__ == "__main__":
    main()
"""
    sandbox._sandbox.write_text_file("/tmp/nexus_playwright_runner.py", full_script)
    result = sandbox._sandbox.commands.run(
        "python3 /tmp/nexus_playwright_runner.py",
        timeout=45,
    )
    exit_code = int(getattr(result, "exit_code", -1) or 0)
    if exit_code != 0:
        return {
            "ok": False,
            "data": {},
            "error": getattr(result, "stderr", "")
            or getattr(result, "stdout", "")
            or "Playwright script failed",
            "error_code": "PLAYWRIGHT_SCRIPT_FAILED",
            "retry_hint": "Inspect the browser and retry with a fresh selector.",
        }
    stdout = str(getattr(result, "stdout", "") or "").strip()
    try:
        for line in reversed(stdout.splitlines()):
            if line.lstrip().startswith("{"):
                parsed = json.loads(line)
                if isinstance(parsed, dict) and "ok" in parsed:
                    return parsed
        raise ValueError("No JSON result line")
    except Exception as exc:
        return {
            "ok": False,
            "data": {},
            "error": f"Could not parse Playwright result: {exc}",
            "error_code": "PLAYWRIGHT_RESULT_INVALID",
            "retry_hint": "Check the Chromium CDP process and retry.",
        }


def _typed_result(
    action: str,
    raw: dict[str, Any],
    *,
    mutation: bool,
    observed: bool = False,
) -> dict[str, Any]:
    if not raw.get("ok"):
        return tool_error(
            str(raw.get("error") or f"Playwright {action} failed"),
            error_code=str(raw.get("error_code") or "PLAYWRIGHT_ERROR"),
            suggested_alternatives=["take_screenshot", "playwright_snapshot"],
            retry_hint=str(raw.get("retry_hint") or ""),
            action=action,
        )
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    if mutation:
        _mark_browser_mutation(f"playwright_{action}")
    if observed:
        _mark_browser_observed()
    return tool_success(
        f"Playwright {action} completed.",
        detail=data,
        action=action,
        cdp_port=settings.browser_cdp_port,
        mutated=mutation,
        observed=observed,
        **data,
    )


@normalized_tool(needs_sandbox=True)
def playwright_navigate(url: str) -> dict[str, Any]:
    """Navigate visible Chromium and return the resulting URL/title."""
    script = f"""
            page.goto({url!r}, wait_until="domcontentloaded", timeout=30000)
            data = {{"url": page.url, "title": page.title()}}
"""
    return _typed_result(
        "navigate",
        _execute_playwright_script(script),
        mutation=True,
    )


@normalized_tool(needs_sandbox=True)
def playwright_click(selector: str) -> dict[str, Any]:
    """Click one DOM element, then report its post-click page state."""
    script = f"""
            locator = page.locator({selector!r}).first
            locator.click(timeout=10000)
            page.wait_for_timeout(250)
            data = {{"selector": {selector!r}, "clicked": True, "url": page.url, "title": page.title()}}
"""
    return _typed_result(
        "click",
        _execute_playwright_script(script),
        mutation=True,
    )


@normalized_tool(needs_sandbox=True)
def playwright_type(selector: str, text: str) -> dict[str, Any]:
    """Fill one DOM field without echoing the entered value."""
    script = f"""
            locator = page.locator({selector!r}).first
            locator.fill({text!r}, timeout=10000)
            data = {{"selector": {selector!r}, "typed_characters": {len(text)}, "url": page.url}}
"""
    return _typed_result(
        "type",
        _execute_playwright_script(script),
        mutation=True,
    )


@normalized_tool(needs_sandbox=True)
def playwright_get_text(selector: str) -> dict[str, Any]:
    """Read visible text and treat it as a fresh DOM observation."""
    script = f"""
            locator = page.locator({selector!r}).first
            text_content = locator.inner_text(timeout=10000)
            data = {{"selector": {selector!r}, "text": text_content, "url": page.url}}
"""
    return _typed_result(
        "get_text",
        _execute_playwright_script(script),
        mutation=False,
        observed=True,
    )


@normalized_tool(needs_sandbox=True)
def playwright_wait_for(selector: str, timeout_ms: int = 10_000) -> dict[str, Any]:
    """Wait for a visible element and return fresh observation evidence."""
    bounded_timeout = max(100, min(int(timeout_ms), 60_000))
    script = f"""
            locator = page.locator({selector!r}).first
            locator.wait_for(state="visible", timeout={bounded_timeout})
            data = {{"selector": {selector!r}, "visible": locator.is_visible(), "url": page.url}}
"""
    return _typed_result(
        "wait_for",
        _execute_playwright_script(script),
        mutation=False,
        observed=True,
    )


@normalized_tool(needs_sandbox=True)
def playwright_snapshot() -> dict[str, Any]:
    """Return a bounded DOM snapshot for action planning and verification."""
    script = """
            text = page.locator("body").inner_text(timeout=10000)[:5000]
            targets = page.locator("a,button,input,select,textarea,[role=button]").evaluate_all(
                '''els => els.slice(0, 50).map((el, index) => ({
                    index,
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").slice(0, 160),
                    id: el.id || "",
                    name: el.getAttribute("name") || "",
                    role: el.getAttribute("role") || "",
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                }))'''
            )
            data = {"url": page.url, "title": page.title(), "text": text, "targets": targets}
"""
    return _typed_result(
        "snapshot",
        _execute_playwright_script(script),
        mutation=False,
        observed=True,
    )


@normalized_tool(needs_sandbox=True)
def playwright_verify(
    selector: str = "body",
    expected_text: str = "",
    expected_url_contains: str = "",
) -> dict[str, Any]:
    """Verify observable DOM state after a browser mutation."""
    script = f"""
            locator = page.locator({selector!r}).first
            visible = locator.is_visible()
            text_content = locator.inner_text(timeout=10000)[:3000] if visible else ""
            text_ok = ({expected_text!r} in text_content) if {bool(expected_text)!r} else True
            url_ok = ({expected_url_contains!r} in page.url) if {bool(expected_url_contains)!r} else True
            verified = bool(visible and text_ok and url_ok)
            data = {{
                "selector": {selector!r},
                "visible": visible,
                "expected_text": {expected_text!r},
                "text_matched": text_ok,
                "expected_url_contains": {expected_url_contains!r},
                "url_matched": url_ok,
                "url": page.url,
                "verified": verified,
                "evidence": text_content[:500],
            }}
"""
    raw = _execute_playwright_script(script)
    if raw.get("ok") and not bool((raw.get("data") or {}).get("verified")):
        return tool_error(
            "Browser verification failed.",
            error_code="VERIFICATION_FAILED",
            suggested_alternatives=["playwright_snapshot", "take_screenshot"],
            detail=raw.get("data") or {},
            retryable=True,
        )
    return _typed_result(
        "verify",
        raw,
        mutation=False,
        observed=True,
    )


__all__ = [
    "playwright_click",
    "playwright_get_text",
    "playwright_navigate",
    "playwright_snapshot",
    "playwright_type",
    "playwright_verify",
    "playwright_wait_for",
]
