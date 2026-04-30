"""Terminal command execution tool."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_MAX_EXCERPT_CHARS = 480
_MAX_SUMMARY_CHARS = 220


def _coerce_exit_code(value: object) -> int:
    try:
        if value is None:
            return -1
        return int(value)
    except (TypeError, ValueError):
        return -1


def _useful_lines(text: str, *, limit: int = 4) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line:
            continue
        lines.append(line)
    if len(lines) <= limit * 2:
        return lines
    return lines[:limit] + lines[-limit:]


def _clip_text(value: str, limit: int) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_output(text: str, *, limit: int = _MAX_EXCERPT_CHARS) -> str:
    if not text:
        return ""
    excerpt = "\n".join(_useful_lines(text))
    excerpt = re.sub(r"\n{3,}", "\n\n", excerpt).strip()
    if len(excerpt) <= limit:
        return excerpt
    return excerpt[: limit - 1].rstrip() + "…"


def _build_summary(command: str, stdout: str, stderr: str, exit_code: int) -> str:
    if exit_code == 0:
        basis = _compact_output(stdout, limit=_MAX_SUMMARY_CHARS) or "Command completed successfully."
    else:
        basis = _compact_output(stderr or stdout, limit=_MAX_SUMMARY_CHARS) or "Command failed."
    return _clip_text(f"{command}: {basis}", _MAX_SUMMARY_CHARS)


def run_command(command: str, background: bool = False) -> dict:
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
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        result = sandbox.run_command(command, timeout=120, background=background)
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        exit_code = _coerce_exit_code(result.get("exit_code", -1))
        compact = {
            "command": command,
            "summary": _build_summary(command, stdout, stderr, exit_code),
            "stdout_excerpt": _compact_output(stdout),
            "stderr_excerpt": _compact_output(stderr),
            "line_count": len(stdout.splitlines()) + len(stderr.splitlines()),
            "truncated": len(stdout) > _MAX_EXCERPT_CHARS or len(stderr) > _MAX_EXCERPT_CHARS,
            "exit_code": exit_code,
        }
        # Reset screenshot cooldown so agent can screenshot right after
        from nexus.tools.screen import _last_call_time
        _last_call_time.t = 0.0
        return compact
    except Exception as e:
        logger.error("run_command failed: %s", e)
        error_text = str(e)
        return {
            "command": command,
            "summary": _clip_text(f"{command}: {error_text}", _MAX_SUMMARY_CHARS),
            "stdout_excerpt": "",
            "stderr_excerpt": _compact_output(error_text),
            "line_count": 0,
            "truncated": False,
            "exit_code": -1,
        }
