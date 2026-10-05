# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Provider-agnostic cleanup of streamed model text.

Gateways that stringify structured reasoning with JavaScript coercion can leak
``"[object Object]"`` and lone ``undefined`` lines into the stream.
:func:`sanitize_stream_text` removes those artifacts and nothing else: words
like ``undefined`` or ``NaN`` inside prose or code are real content.

Part classification (reasoning / narration / answer) lives in
:mod:`nexus.turn_output`.
"""

from __future__ import annotations

import re
from typing import Any

# JS object/array coercion artifacts that must never reach the user. A gateway
# that stringifies a structured reasoning payload with JavaScript coercion emits
# "[object Object]" (or ",[object Object]," when array-joined). Match runs of
# them plus any adjacent comma/space so the surrounding text stays readable.
_COERCION_ARTIFACT_RE = re.compile(
    r"\s*,?\s*\[object (?:Object|Array|Null|Undefined)\]\s*,?",
    re.IGNORECASE,
)

# A line holding only a JS sentinel is a coercion of a missing value.
_SENTINEL_LINE_RE = re.compile(r"^[ \t]*(?:undefined|NaN|null)[ \t]*$")
_FENCE_RE = re.compile(r"^\s*```")


def _drop_sentinel_lines(text: str) -> str:
    lines = text.split("\n")
    kept: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            kept.append(line)
            continue
        if not in_fence and _SENTINEL_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def sanitize_stream_text(text: Any) -> str:
    """Return user-safe text with coercion artifacts removed.

    Accepts any input; non-strings are coerced defensively. Returns an empty
    string when the input is empty or becomes empty after cleaning.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""
    if not text:
        return ""
    cleaned = _COERCION_ARTIFACT_RE.sub(" ", text)
    cleaned = _drop_sentinel_lines(cleaned)
    return cleaned.strip()


def sanitize_stream_delta(text: Any) -> str:
    """Clean one streamed chunk without trimming: spaces between chunks matter."""
    if not isinstance(text, str) or not text:
        return ""
    return _COERCION_ARTIFACT_RE.sub(" ", text)


__all__ = ["sanitize_stream_delta", "sanitize_stream_text"]
