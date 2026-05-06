# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Playwright-based browser tools via CDP."""

from __future__ import annotations

import json
import logging
from typing import Any

from nexus.tools.base import normalized_tool
from nexus.tools._context import get_sandbox

logger = logging.getLogger(__name__)

_PLAYWRIGHT_INSTALLED = False

def _ensure_playwright_installed() -> None:
    global _PLAYWRIGHT_INSTALLED
    if _PLAYWRIGHT_INSTALLED:
        return
        
    sandbox = get_sandbox()
    logger.info("Checking for Playwright in sandbox...")
    res = sandbox._sandbox.commands.run("python3 -c 'import playwright'", timeout=15)
    if res.exit_code != 0:
        logger.info("Installing playwright...")
        sandbox._sandbox.commands.run("pip install playwright && playwright install chromium", timeout=120)
    _PLAYWRIGHT_INSTALLED = True

def _execute_playwright_script(script_body: str) -> dict[str, Any]:
    _ensure_playwright_installed()
    sandbox = get_sandbox()
    
    full_script = f'''
import json
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError as e:
    print(json.dumps({{"ok": False, "data": {{}}, "error": "Playwright not installed properly: " + str(e), "retry_hint": "Try reinstalling playwright."}}))
    sys.exit(0)

def main():
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            
            # --- USER SCRIPT START ---
{script_body}
            # --- USER SCRIPT END ---
            
            print(json.dumps({{"ok": True, "data": data, "error": None, "retry_hint": None}}))
    except Exception as e:
        print(json.dumps({{"ok": False, "data": {{}}, "error": str(e), "retry_hint": "Check selector, URL, or CDP connection."}}))

if __name__ == "__main__":
    main()
'''
    sandbox._sandbox.write_text_file("/tmp/pw_runner.py", full_script)
    
    res = sandbox._sandbox.commands.run("python3 /tmp/pw_runner.py", timeout=45)
    
    if res.exit_code != 0:
        err = res.stderr or res.stdout or "Unknown error"
        return {
            "ok": False, 
            "data": {}, 
            "error": err, 
            "retry_hint": "Script execution failed."
        }
        
    stdout = (res.stdout or "").strip()
    try:
        for line in reversed(stdout.splitlines()):
            if line.startswith("{") and "ok" in line:
                return json.loads(line)
        return json.loads(stdout)
    except Exception as e:
        return {
            "ok": False, 
            "data": {}, 
            "error": f"Parse error: {e}. Output was: {stdout}", 
            "retry_hint": "Check CDP connection (localhost:9222)."
        }

@normalized_tool
def playwright_navigate(url: str) -> dict[str, Any]:
    """Navigate the Chromium browser to a URL using Playwright via CDP."""
    safe_url = url.replace("'", "\\'").replace('"', '\\"')
    script = f"""
            page.goto('{safe_url}', timeout=30000)
            data = {{"url": page.url}}
"""
    return _execute_playwright_script(script)

@normalized_tool
def playwright_click(selector: str) -> dict[str, Any]:
    """Click an element in the browser using Playwright."""
    safe_selector = selector.replace("'", "\\'").replace('"', '\\"')
    script = f"""
            page.click('{safe_selector}', timeout=10000)
            data = {{"clicked": '{safe_selector}'}}
"""
    return _execute_playwright_script(script)

@normalized_tool
def playwright_type(selector: str, text: str) -> dict[str, Any]:
    """Type text into an element in the browser using Playwright."""
    safe_selector = selector.replace("'", "\\'").replace('"', '\\"')
    safe_text = text.replace("'", "\\'").replace('"', '\\"')
    script = f"""
            page.fill('{safe_selector}', '{safe_text}', timeout=10000)
            data = {{"typed": '{safe_text}', "selector": '{safe_selector}'}}
"""
    return _execute_playwright_script(script)

@normalized_tool
def playwright_get_text(selector: str) -> dict[str, Any]:
    """Get the text content of an element in the browser using Playwright."""
    safe_selector = selector.replace("'", "\\'").replace('"', '\\"')
    script = f"""
            element = page.locator('{safe_selector}').first
            text_content = element.text_content(timeout=10000)
            data = {{"text": text_content}}
"""
    return _execute_playwright_script(script)

@normalized_tool
def playwright_wait_for(selector: str, timeout_ms: int) -> dict[str, Any]:
    """Wait for an element to be visible in the browser using Playwright."""
    safe_selector = selector.replace("'", "\\'").replace('"', '\\"')
    script = f"""
            page.wait_for_selector('{safe_selector}', state='visible', timeout={timeout_ms})
            data = {{"waited_for": '{safe_selector}'}}
"""
    return _execute_playwright_script(script)
