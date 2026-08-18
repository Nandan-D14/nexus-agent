# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared model-boundary integrity helpers for all LiteLLM router clients.

Every provider client (Vultr, Qwen, Bynara) runs the same OpenAI-compatible
boundary and inherits the same failure class: a model that batches multiple
tool calls into one assistant turn — or returns tool calls with missing or
duplicate ``id`` fields — corrupts request/response correlation and can trigger
the *same* side effect twice (e.g. sending an email twice).

Rather than patch each router separately, both guards live here and are applied
uniformly:

* :func:`apply_tool_call_policy` — request side: pin ``parallel_tool_calls`` to
  ``False`` for tool-enabled calls, matching the planner's one-tool-per-loop
  contract. The caller may still override it explicitly.
* :func:`repair_tool_call_ids` — response side: on a materialized (non-stream)
  response, ensure every tool call carries a unique, non-empty ``id`` so the
  agent runtime correlates each call to exactly one result.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from nexus.config import settings

logger = logging.getLogger(__name__)


def apply_tool_call_policy(kwargs: dict[str, Any], tools: Any) -> dict[str, Any]:
    """Return kwargs with a one-tool-per-turn policy for tool-enabled requests.

    No-op when the request carries no tools, when the policy is disabled, or when
    the caller already set ``parallel_tool_calls`` explicitly.
    """
    if not tools or not settings.disable_parallel_tool_calls:
        return kwargs
    if "parallel_tool_calls" in kwargs:
        return kwargs
    updated = dict(kwargs)
    updated["parallel_tool_calls"] = False
    return updated


def apply_request_timeout(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return kwargs carrying a request deadline for the model call.

    LiteLLM has no default wall clock, so a gateway that accepts the
    connection and then stalls would hold the agent turn open indefinitely.
    An explicit ``timeout`` turns that into a retryable error. A caller-set
    value always wins; ``model_request_timeout_seconds <= 0`` disables it.
    """
    if "timeout" in kwargs:
        return kwargs
    timeout = float(getattr(settings, "model_request_timeout_seconds", 0) or 0)
    if timeout <= 0:
        return kwargs
    updated = dict(kwargs)
    updated["timeout"] = timeout
    return updated


def _iter_message_tool_calls(response: Any):
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not isinstance(choices, (list, tuple)):
        return
    for choice in choices:
        message = getattr(choice, "message", None)
        if message is None and isinstance(choice, dict):
            message = choice.get("message")
        if message is None:
            continue
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls is None and isinstance(message, dict):
            tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, (list, tuple)) and tool_calls:
            yield tool_calls


def _get_call_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or "")
    return str(getattr(call, "id", "") or "")


def _set_call_id(call: Any, value: str) -> None:
    if isinstance(call, dict):
        call["id"] = value
    else:
        try:
            call.id = value
        except Exception:  # pragma: no cover - immutable provider object
            pass


def repair_tool_call_ids(response: Any) -> Any:
    """Ensure tool calls on a materialized response have unique, non-empty IDs.

    Best-effort and side-effect free for anything that is not a plain
    non-streaming response object (streaming wrappers are left untouched — the
    request-side policy and the gateway normalizer cover that path).
    """
    try:
        for tool_calls in _iter_message_tool_calls(response):
            seen: set[str] = set()
            for index, call in enumerate(tool_calls):
                call_id = _get_call_id(call)
                if not call_id or call_id in seen:
                    new_id = f"call_{uuid.uuid4().hex[:24]}"
                    _set_call_id(call, new_id)
                    logger.warning(
                        "Repaired tool-call id at index %d (was %r) -> %s",
                        index,
                        call_id,
                        new_id,
                    )
                    call_id = new_id
                seen.add(call_id)
    except Exception:  # pragma: no cover - never break a completion on repair
        logger.debug("tool-call id repair skipped", exc_info=True)
    return response


__all__ = ["apply_request_timeout", "apply_tool_call_policy", "repair_tool_call_ids"]
