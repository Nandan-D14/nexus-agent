# Copyright (c) 2026 nandan-d14. All rights reserved.
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


from nexus.tools.base import normalized_tool, reraise_if_sandbox_dead

@normalized_tool(needs_sandbox=True)
async def run_command(command: str, background: bool = False, cwd: str | None = None) -> dict:
    """Run a shell command in the Linux terminal and return the output.

    Use this to execute any bash command: file operations, package installs,
    running scripts, git commands, system commands, etc.

    For GUI applications (like file managers, browsers, text editors) that
    stay open, set background=True so the command doesn't block.

    Args:
        command: The bash command to execute.
        background: If True, launch the command in the background. Use for
            GUI apps or long-running processes that don't exit immediately.
        cwd: Optional working directory for the command. Defaults to the active
            workspace path if available, or "~".

    Returns:
        dict with stdout, stderr, and exit_code.
    """
    from nexus.tools.sandbox_events import emit_sandbox_event, redact_command_text

    target_cwd = (cwd or "").strip()
    if not target_cwd or target_cwd == "~":
        try:
            from nexus.tools.workspace import get_active_workspace_path
            target_cwd = get_active_workspace_path()
        except Exception:
            target_cwd = "~"

    visible_command = redact_command_text(command)
    await emit_sandbox_event({
        "type": "sandbox_terminal",
        "phase": "start",
        "command": visible_command,
        "cwd": target_cwd,
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
                "cwd": target_cwd,
                "stdout": "",
                "stderr": message,
                "exit_code": 0,
            })
            return compact

        from nexus.tools._context import get_sandbox
        from nexus.tools.preview_hosts import (
            command_starts_long_running_server,
            ensure_vite_preview_hosts,
        )

        sandbox = get_sandbox()
        effective_cwd = target_cwd if target_cwd != "~" else None
        starts_server = command_starts_long_running_server(command)
        effective_background = background or starts_server
        if starts_server:
            try:
                roots = [effective_cwd or "", target_cwd]
                try:
                    from nexus.tools.workspace import get_active_workspace_path

                    roots.append(get_active_workspace_path())
                except Exception:
                    pass
                ensure_vite_preview_hosts(sandbox, *roots)
            except Exception:
                logger.debug("Vite host patch before dev server start failed", exc_info=True)
        result = await asyncio.to_thread(
            lambda: sandbox.run_command(
                command,
                timeout=120,
                background=effective_background,
                cwd=effective_cwd,
            ),
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
        if starts_server and not background:
            compact["summary"] = _clip_text(
                compact["summary"] + " (auto-backgrounded long-running server)",
                _MAX_SUMMARY_CHARS,
            )
        if exit_code != 0:
            compact["error_code"] = "NONZERO_EXIT"
            compact["retryable"] = True

        # Auto-detect web dev servers so Preview can attach without a second tool call.
        if effective_background or starts_server:
            try:
                await asyncio.sleep(0.8)
                ports = await asyncio.to_thread(sandbox.find_listening_web_ports)
                if ports:
                    primary_port = ports[0]
                    try:
                        from nexus.tools.docs import publish_app_preview
                        preview_res = await publish_app_preview(primary_port, title="App Preview")
                        if preview_res.get("status") == "success":
                            preview_url = preview_res.get("detail", {}).get("url") or ""
                            compact["artifacts"] = [{"port": primary_port, "kind": "app_preview", "url": preview_url}]
                            compact["summary"] += f" (Live preview published on port {primary_port})"
                    except Exception:
                        pass
            except Exception:
                pass

        from nexus.tools.screen import _last_call_time
        _last_call_time.t = 0.0
        await emit_sandbox_event({
            "type": "sandbox_terminal",
            "phase": "result",
            "command": visible_command,
            "cwd": target_cwd,
            "stdout": _compact_output(stdout, limit=_MAX_PANE_CHARS),
            "stderr": _compact_output(stderr, limit=_MAX_PANE_CHARS),
            "exit_code": exit_code,
        })
        return compact
    except Exception as e:
        reraise_if_sandbox_dead(e)
        logger.error("run_command failed: %s", e)
        error_text = str(e)
        await emit_sandbox_event({
            "type": "sandbox_terminal",
            "phase": "result",
            "command": visible_command,
            "cwd": target_cwd,
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
