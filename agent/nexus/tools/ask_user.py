# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""ask_user — pause the run and ask the user one focused question."""

from __future__ import annotations

import logging
from typing import Any

from nexus.tools._context import get_ask_user_callback
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


@normalized_tool
async def ask_user(question: str) -> dict[str, Any]:
    """Ask the user ONE focused question and wait for their reply.

    Use only when a required input is genuinely missing or the request is
    ambiguous in a way you cannot resolve yourself. Do not use it to ask for
    permission (approvals have their own flow) or to report progress.

    Args:
        question: A single, specific question the user can answer in one message.

    Returns:
        NormalizedToolResult with the user's answer, or an error if the user
        did not answer in time.
    """
    clean = (question or "").strip()
    if not clean:
        return tool_error("question is required", error_code="INVALID_INPUT")
    if len(clean) > 600:
        clean = clean[:599] + "…"

    callback = get_ask_user_callback()
    if callback is None:
        return tool_error(
            "ask_user is not available in this run context. Continue with your "
            "best assumption and state it clearly in your final answer.",
            error_code="ASK_USER_UNAVAILABLE",
        )

    try:
        answer = await callback(clean)
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
    )
