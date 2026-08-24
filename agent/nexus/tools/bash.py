# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Terminal command execution tool."""

from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

_MAX_EXCERPT_CHARS = 8_000
_MAX_SUMMARY_CHARS = 220
_MAX_PANE_CHARS = 12_000


def _coerce_exit_code(value: object) -> int:
    try:
        if value is None:
            return -1
        return int(value)
    except (TypeError, ValueError):
        return -1


def _clip_text(value: str, limit: int) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_output(text: str, *, limit: int = _MAX_EXCERPT_CHARS) -> str:
    if not text:
        return ""
    excerpt = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(excerpt) <= limit:
        return excerpt
    return excerpt[: limit - 1].rstrip() + "…"


def _build_summary(command: str, stdout: str, stderr: str, exit_code: int) -> str:
    if exit_code == 0:
        basis = _compact_output(stdout, limit=_MAX_SUMMARY_CHARS) or "Command completed successfully."
    else:
        basis = _compact_output(stderr or stdout, limit=_MAX_SUMMARY_CHARS) or "Command failed."
    return _clip_text(f"{command}: {basis}", _MAX_SUMMARY_CHARS)


_BINARY_DUMP_RE = re.compile(
    r"(?is)\b(cat|base64)\s+[^;&|]*(?:\.pdf\b|pdf_base64\.txt\b|base64\.txt\b)"
)


def _blocked_binary_dump(command: str) -> bool:
    return bool(_BINARY_DUMP_RE.search(command or ""))


from nexus.tools.base import normalized_tool

@normalized_tool(needs_sandbox=True)
async def run_command(command: str, background: bool = False) -> dict:
    """Run a shell command in the Linux terminal and return the output.

    Use this to execute any bash command: file operations, package installs,
    running scripts, git commands, system commands, etc.

    For GUI applications (like file managers, browsers, text editors) that
    stay open, set background=True so the command doesn't block.

    Args:
        command: The bash command to execute.
        background: If True, launch the command in the background. Use for
            GUI apps or long-running processes that don't exit immediately.

    Returns:
        dict with stdout, stderr, and exit_code.
    """
    from nexus.tools.sandbox_events import emit_sandbox_event, redact_command_text

    visible_command = redact_command_text(command)
    await emit_sandbox_event({
        "type": "sandbox_terminal",
        "phase": "start",
        "command": visible_command,
        "cwd": "~",
    })
    try:
        if _blocked_binary_dump(command):
            message = (
                "Skipped PDF/base64 dump. PDFs should be returned as artifacts; "
                "use extract_pdf_text(path=...) only when you need to read their text."
            )
            compact = {
                "status": "success",
                "command": command,
                "summary": message,
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "line_count": 0,
                "truncated": False,
                "exit_code": 0,
            }
            await emit_sandbox_event({
                "type": "sandbox_terminal",
                "phase": "result",
                "command": visible_command,
                "cwd": "~",
                "stdout": "",
                "stderr": message,
                "exit_code": 0,
            })
            return compact

        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        result = await asyncio.to_thread(
            lambda: sandbox.run_command(command, timeout=120, background=background),
        )
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        exit_code = _coerce_exit_code(result.get("exit_code", -1))
        compact = {
            "status": "success" if exit_code == 0 else "error",
            "command": command,
            "summary": _build_summary(command, stdout, stderr, exit_code),
            "stdout_excerpt": _compact_output(stdout),
            "stderr_excerpt": _compact_output(stderr),
            "line_count": len(stdout.splitlines()) + len(stderr.splitlines()),
            "truncated": len(stdout) > _MAX_EXCERPT_CHARS or len(stderr) > _MAX_EXCERPT_CHARS,
            "exit_code": exit_code,
        }
        if exit_code != 0:
            compact["error_code"] = "NONZERO_EXIT"
            compact["retryable"] = True
        from nexus.tools.screen import _last_call_time
        _last_call_time.t = 0.0
        await emit_sandbox_event({
            "type": "sandbox_terminal",
            "phase": "result",
            "command": visible_command,
            "cwd": "~",
            "stdout": _compact_output(stdout, limit=_MAX_PANE_CHARS),
            "stderr": _compact_output(stderr, limit=_MAX_PANE_CHARS),
            "exit_code": exit_code,
        })
        return compact
    except Exception as e:
        logger.error("run_command failed: %s", e)
        error_text = str(e)
        await emit_sandbox_event({
            "type": "sandbox_terminal",
            "phase": "result",
            "command": visible_command,
            "cwd": "~",
            "stdout": "",
            "stderr": _compact_output(error_text, limit=_MAX_PANE_CHARS),
            "exit_code": -1,
        })
        return {
            "status": "error",
            "command": command,
            "summary": _clip_text(f"{command}: {error_text}", _MAX_SUMMARY_CHARS),
            "stdout_excerpt": "",
            "stderr_excerpt": _compact_output(error_text),
            "line_count": 0,
            "truncated": False,
            "exit_code": -1,
            "error_code": "COMMAND_EXCEPTION",
            "retryable": True,
        }
