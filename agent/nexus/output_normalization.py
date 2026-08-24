# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Provider-agnostic normalization and classification of streamed model output.

Reasoning models — and gateways that fold ``reasoning_content`` into the plain
message text (e.g. the Vultr ``-normalize`` mode) — can leak raw chain-of-thought
and JS coercion artifacts (``"[object Object]"``, stray ``undefined``/``null``)
into the user-facing stream. These helpers centralize two concerns so the
orchestrator can apply a single visibility/persistence policy regardless of
which provider or model is in use:

* :func:`sanitize_stream_text` strips coercion/garbage tokens from any text.
* :func:`classify_part` labels a streamed content part as ``"answer"`` or
  ``"reasoning"`` using whatever signal the provider exposes.
"""

from __future__ import annotations

import re
from typing import Any, Literal

PartKind = Literal["answer", "reasoning"]

# JS object/array coercion artifacts that must never reach the user. A gateway
# that stringifies a structured reasoning payload with JavaScript coercion emits
# "[object Object]" (or ",[object Object]," when array-joined). Match runs of
# them plus any adjacent comma/space so the surrounding text stays readable.
_COERCION_ARTIFACT_RE = re.compile(
    r"\s*,?\s*\[object (?:Object|Array|Null|Undefined)\]\s*,?",
    re.IGNORECASE,
)

# Stray JS sentinel tokens that only appear via coercion of missing values.
# Only strip them when they stand alone (surrounded by non-word chars) so real
# prose like "nullable" or "undefined behavior" is left intact.
_STRAY_SENTINEL_RE = re.compile(
    r"(?<![\w'-])(?:undefined|NaN)(?![\w'-])",
)

_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def sanitize_stream_text(text: Any) -> str:
    """Return user-safe text with coercion artifacts removed.

    Accepts any input; non-strings are coerced defensively (never producing
    ``"[object Object]"`` the way JS would). Returns an empty string when the
    input is empty or becomes empty after cleaning.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        # Defensive: a well-behaved caller passes strings, but never emit a
        # raw ``repr``/coercion of a dict to the user.
        try:
            text = str(text)
        except Exception:
            return ""
    if not text:
        return ""
    cleaned = _COERCION_ARTIFACT_RE.sub(" ", text)
    cleaned = _STRAY_SENTINEL_RE.sub(" ", cleaned)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned)
    # Trim spaces that now hug newlines, then strip the ends.
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def classify_part(part: Any, *, reasoning_is_text: bool = False) -> PartKind:
    """Classify a non-final model content part as answer or reasoning.

    Priority of signals:
    1. ``part.thought`` truthy (Google Gemini thinking parts).
    2. A dedicated ``reasoning_content`` / ``reasoning`` field on the part.
    3. ``reasoning_is_text``: for gateways/models that fold reasoning into plain
       text, treat non-final text as reasoning (the caller only invokes this for
       non-final parts; the final answer is handled separately).

    Defaults to ``"answer"`` so non-reasoning providers keep prior behavior.
    """
    return "reasoning" if is_reasoning_part(part, reasoning_is_text=reasoning_is_text) else "answer"


def is_reasoning_part(part: Any, *, reasoning_is_text: bool = False) -> bool:
    """Single source of truth for "is this content part reasoning, not answer".

    Used at every consumption point (streaming emit AND final-answer selection)
    so reasoning is never mistaken for the user-facing answer. See
    :func:`classify_part` for the signal priority.
    """
    if bool(getattr(part, "thought", False)):
        return True
    if getattr(part, "reasoning_content", None) or getattr(part, "reasoning", None):
        return True
    return bool(reasoning_is_text)


__all__ = ["PartKind", "sanitize_stream_text", "classify_part", "is_reasoning_part"]
