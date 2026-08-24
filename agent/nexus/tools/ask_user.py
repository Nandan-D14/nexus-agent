# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""ask_user — pause the run and ask the user one focused question."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from nexus.tools._context import get_ask_user_callback
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)

_MAX_OPTIONS = 6
_MIN_OPTIONS = 2
_MAX_OPTION_CHARS = 80
_NUMBERED_LINE = re.compile(r"^\s*\d+[.)]\s+\S+")


def normalize_ask_user_options(raw: Any) -> list[str] | None:
    """Coerce a model-supplied options value into 2–6 unique short labels."""
    if raw is None or raw is False:
        return None
    values: list[Any]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text[:1] in "[{":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                values = parsed
            elif isinstance(parsed, dict):
                values = list(parsed.values())
            else:
                values = [line.strip() for line in text.splitlines() if line.strip()]
        else:
            values = [line.strip() for line in text.splitlines() if line.strip()]
    elif isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        return None

    labels: list[str] = []
    seen: set[str] = set()
    for item in values:
        label = " ".join(str(item or "").split())
        if not label:
            continue
        label = re.sub(r"^\d+[.)]\s+", "", label).strip()
        if not label:
            continue
        if len(label) > _MAX_OPTION_CHARS:
            label = label[: _MAX_OPTION_CHARS - 1] + "…"
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
        if len(labels) >= _MAX_OPTIONS:
            break
    return labels if len(labels) >= _MIN_OPTIONS else None


def format_ask_user_history_text(question: str, options: list[str] | None) -> str:
    """Persist the heading plus numbered choices so history can restore the picker."""
    heading = (question or "").strip()
    if not options:
        return heading
    if any(_NUMBERED_LINE.match(line) for line in heading.splitlines()):
        return heading
    numbered = "\n".join(f"{index}. {label}" for index, label in enumerate(options, start=1))
    return f"{heading}\n\n{numbered}"


@normalized_tool
async def ask_user(
    question: str,
    options: list[str] | None = None,
) -> dict[str, Any]:
    """Ask the user ONE focused question and wait for their reply.

    Use only when a required input is genuinely missing or the request is
    ambiguous in a way you cannot resolve yourself. Do not use it to ask for
    permission (approvals have their own flow) or to report progress.

    Args:
        question: A single, specific question. Keep this as the heading; do not
            bury the choices inside it when you also pass ``options``.
        options: Optional 2–6 short choices for a multiple-choice picker. Pass
            this whenever the user is choosing between approaches. Include
            "Something else" when a custom answer might be needed. Omit for
            answers that must be typed (path, id, email, name).

    Returns:
        NormalizedToolResult with the user's answer, or an error if the user
        did not answer in time.
    """
    clean = (question or "").strip()
    if not clean:
        return tool_error("question is required", error_code="INVALID_INPUT")
    if len(clean) > 600:
        clean = clean[:599] + "…"

    choices = normalize_ask_user_options(options)

    callback = get_ask_user_callback()
    if callback is None:
        return tool_error(
            "ask_user is not available in this run context. Continue with your "
            "best assumption and state it clearly in your final answer.",
            error_code="ASK_USER_UNAVAILABLE",
        )

    try:
        answer = await callback(clean, choices)
    except TypeError:
        try:
            answer = await callback(clean)
        except Exception as exc:
            logger.warning("ask_user callback failed", exc_info=True)
            return tool_error(f"ask_user failed: {exc}", error_code="ASK_USER_FAILED")
    except Exception as exc:
        logger.warning("ask_user callback failed", exc_info=True)
        return tool_error(f"ask_user failed: {exc}", error_code="ASK_USER_FAILED")

    if answer is None or not str(answer).strip():
        return tool_error(
            "The user did not answer in time. Continue with your best assumption "
            "and state it clearly in your final answer.",
            error_code="ASK_USER_TIMEOUT",
        )

    return tool_success(
        f"User answered: {str(answer).strip()}",
        question=clean,
        answer=str(answer).strip(),
        options=choices or [],
    )
