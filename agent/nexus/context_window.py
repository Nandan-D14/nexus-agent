# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Context-window budgeting for LLM turns.

The ADK Runner re-sends the full session history every turn. Without a cap the
prompt grows past the model's context limit (e.g. Kimi-K2.6 = 262144 tokens),
raising ``BadRequestError: input exceeds the model context limit``.

``make_context_trimmer`` returns an ADK ``before_model_callback`` that trims the
oldest ``llm_request.contents`` so the per-turn prompt stays under a budget
derived from the model limit, always preserving the system instruction and the
most recent turns. Trimming is char/4 estimated (deterministic, no extra deps)
with a safety margin, and it avoids orphaning tool responses.
"""

from __future__ import annotations

import logging

from google.genai import types

from nexus.config import settings

logger = logging.getLogger(__name__)

_TRIM_NOTE = (
    "[earlier turns trimmed to fit the model context window; full history is "
    "preserved in the durable session store]"
)
# Rough chars-per-token; conservative so we under-estimate the budget usage.
_CHARS_PER_TOKEN = 4
# Per-message structural overhead (role markers, delimiters).
_MESSAGE_OVERHEAD_TOKENS = 8


def _estimate_tokens_from_text(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _estimate_tokens_for_content(content) -> int:
    chars = 0
    for part in getattr(content, "parts", None) or []:
        text = getattr(part, "text", None)
        if text:
            chars += len(text)
        fc = getattr(part, "function_call", None)
        if fc is not None:
            chars += len(str(getattr(fc, "args", "") or ""))
            chars += len(getattr(fc, "name", "") or "")
        fr = getattr(part, "function_response", None)
        if fr is not None:
            chars += len(str(getattr(fr, "response", "") or ""))
    return chars // _CHARS_PER_TOKEN + _MESSAGE_OVERHEAD_TOKENS


def _estimate_system_tokens(llm_request) -> int:
    config = getattr(llm_request, "config", None)
    system = getattr(config, "system_instruction", None) if config else None
    if not system:
        return 0
    if isinstance(system, str):
        return _estimate_tokens_from_text(system)
    # types.Content or list of Content/parts — fall back to a string estimate.
    return _estimate_tokens_from_text(str(system))


def _has_function_response(content) -> bool:
    return any(
        getattr(part, "function_response", None) is not None
        for part in (getattr(content, "parts", None) or [])
    )


def _has_function_call(content) -> bool:
    return any(
        getattr(part, "function_call", None) is not None
        for part in (getattr(content, "parts", None) or [])
    )


def _drop_leading_orphan_tool_results(kept: list) -> list:
    """Drop leading tool-response turns whose matching call was trimmed.

    A ``function_response`` with no preceding ``function_call`` in-context makes
    the model API reject the request, so strip any such orphans at the front.
    """
    index = 0
    while index < len(kept) - 1 and _has_function_response(kept[index]):
        index += 1
    return kept[index:]


def _drop_trailing_orphan_tool_calls(kept: list) -> list:
    """Drop trailing ``function_call`` turns that have no following response.

    A turn-cap break can leave a bare ``function_call`` at the tail with no
    matching ``function_response``; the next API call rejects that. Strip such
    trailing orphans so the resend stays valid.
    """
    while (
        len(kept) > 1
        and _has_function_call(kept[-1])
        and not _has_function_response(kept[-1])
    ):
        kept = kept[:-1]
    return kept


def make_context_trimmer():
    """Return a before_model_callback that budgets the prompt to the context window."""

    def before_model_callback(callback_context, llm_request):
        if not settings.enforce_context_budget:
            return None
        contents = list(getattr(llm_request, "contents", None) or [])
        if len(contents) <= 1:
            return None

        limit = max(1000, int(settings.model_context_limit))
        budget = int(limit * float(settings.context_input_budget_ratio))
        available = budget - _estimate_system_tokens(llm_request)
        if available <= 0:
            available = budget

        kept: list = []
        total = 0
        for content in reversed(contents):
            tokens = _estimate_tokens_for_content(content)
            if kept and total + tokens > available:
                break
            kept.append(content)
            total += tokens
        kept.reverse()
        if not kept:
            kept = [contents[-1]]
        kept = _drop_leading_orphan_tool_results(kept)
        # Repair a bare trailing function_call (e.g. left by a turn-cap break)
        # that has no matching function_response, which would 400 the resend.
        kept = _drop_trailing_orphan_tool_calls(kept)

        if len(kept) < len(contents):
            note = types.Content(
                role="user",
                parts=[types.Part(text=_TRIM_NOTE)],
            )
            kept = [note, *kept]
            llm_request.contents = kept
            logger.info(
                "Context trimmed to fit window: %d -> %d messages (~%d/%d token budget)",
                len(contents),
                len(kept),
                total,
                available,
            )
        return None

    return before_model_callback
