# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Unified secret/PII redaction for logs, previews, and audit trails."""

from __future__ import annotations

import re
from typing import Any

_SECRET_KEY_RE = re.compile(
    r"(authorization|cookie|credential|password|secret|token|"
    r"api[_-]?key|apikey|private[_-]?key|client_secret|access_token|"
    r"refresh_token|bearer|session_key)",
    re.IGNORECASE,
)

_INLINE_VALUE_RES = (
    re.compile(r"\bsk-[A-Za-z0-9._-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bxox[bap]-[A-Za-z0-9-]+\b"),
    re.compile(r"\bya29\.[A-Za-z0-9._-]+\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{8,}", re.IGNORECASE),
)


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(str(key or "")))


def redact_inline_values(text: str) -> str:
    redacted = str(text or "")
    for pattern in _INLINE_VALUE_RES:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def redact_sensitive(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, raw in value.items():
            if is_secret_key(str(key)):
                redacted[str(key)] = "***"
            else:
                redacted[str(key)] = redact_sensitive(raw, _depth=_depth + 1)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item, _depth=_depth + 1) for item in value]
    if isinstance(value, str):
        return redact_inline_values(value)
    return value


__all__ = ["is_secret_key", "redact_inline_values", "redact_sensitive"]
