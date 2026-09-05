# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Computer-pane events for live Terminal and Editor takeovers.

ADK AgentTool does not forward nested tool events to the parent runner.
These helpers emit WebSocket frames directly from the tools so planner-direct
and worker-nested calls look the same in the UI.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_EDITOR_CONTENT_LIMIT = 20_000
_INLINE_SECRET_RE = re.compile(
    r"(?i)((?:api[_-]?key|token|secret|password|authorization|bearer|orca_key|"
    r"cookie|credential|private[_-]?key|client_secret)"
    r"\s*[=:]\s*['\"]?)([^\s'\"]+)"
)
_SK_TOKEN_RE = re.compile(
    r"(\bsk-[A-Za-z0-9._-]{8,}\b|\bAKIA[0-9A-Z]{16}\b|"
    r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b|\bxox[bap]-[A-Za-z0-9-]+\b|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def redact_command_text(command: str) -> str:
    """Strip inline key assignments and known token formats from commands."""
    from nexus.redact import redact_inline_values

    text = _INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}[redacted]", command or "")
    text = _SK_TOKEN_RE.sub("[redacted]", text)
    return redact_inline_values(text)


def clip_editor_content(content: str | None, *, limit: int = _EDITOR_CONTENT_LIMIT) -> str:
    text = content if isinstance(content, str) else ("" if content is None else str(content))
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def emit_sandbox_event(payload: dict[str, Any]) -> None:
    """Best-effort UI event. Never raise into the tool body."""
    from nexus.mcp_client import redact_sensitive
    from nexus.tools._context import get_send_json

    send_json = get_send_json()
    if send_json is None:
        return
    try:
        await send_json(redact_sensitive(payload))
    except Exception:
        logger.debug("Failed to emit sandbox UI event", exc_info=True)
