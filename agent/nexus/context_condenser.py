# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""LLM context condenser and todo recitation (``before_model_callback`` pieces).

The trimmer in :mod:`nexus.context_window` keeps prompts under budget by
dropping the oldest messages, which silently loses the goal, decisions, and
artifact ids on long tasks. The condenser runs first: once the prompt passes
``context_condense_trigger_ratio`` of the budget it replaces the oldest block
with one structured summary written by the micro model, keeping the newest
``context_condense_keep_ratio`` raw. Summaries are incremental (previous
summary + newly aged-out messages) and cached per session/agent, so the
model call happens roughly once per ~third of the budget, not every step.
Any failure falls back to the trimmer's plain drop.

Todo recitation re-states the live plan at the end of the planner prompt
mid-loop so the goal stays in the model's recent attention window.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import logging
import threading
from typing import Any

from google.genai import types

from nexus.config import settings
from nexus.context_window import (
    _estimate_system_tokens,
    _estimate_tokens_for_content,
    _estimate_tokens_for_tools,
    _estimate_tokens_from_text,
    _has_function_call,
    _has_function_response,
    _input_token_budget,
    make_context_trimmer,
)

logger = logging.getLogger(__name__)

CONDENSED_PREFIX = "[CONDENSED HISTORY — summary of earlier turns in this task]\n"
_STATE_KEY = "nexus_condensed_context"
_MAX_CACHE_ENTRIES = 1024
_PART_TEXT_CLIP = 1_500
_CALL_ARGS_CLIP = 300
_RESPONSE_CLIP = 700

_CONDENSER_SYSTEM = (
    "You compress an AI agent's working history so it can continue the task "
    "without the original messages. Be factual and terse; never invent. "
    "Output plain text with exactly these headings, omitting empty ones:\n"
    "GOAL: the user's overall request and hard constraints.\n"
    "DONE: completed steps and their verified outcomes.\n"
    "DECISIONS: choices made and why.\n"
    "ARTIFACTS & FILES: exact paths, artifact ids, URLs produced or used.\n"
    "KEY FACTS: data, numbers, names, findings needed later.\n"
    "FAILURES: errors hit and approaches that did not work (do not retry).\n"
    "OPEN: remaining todo items and the immediate next step.\n"
    "Keep it under 600 words."
)


@dataclass(frozen=True)
class _CondensedState:
    upto: int
    fingerprint: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"upto": self.upto, "fingerprint": self.fingerprint, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: Any) -> "_CondensedState | None":
        if not isinstance(data, dict):
            return None
        try:
            return cls(int(data["upto"]), str(data["fingerprint"]), str(data["summary"]))
        except (KeyError, TypeError, ValueError):
            return None


_cache: dict[str, _CondensedState] = {}
_cache_lock = threading.Lock()


def _content_digest(content) -> str:
    digest = hashlib.sha1()
    digest.update(str(getattr(content, "role", "") or "").encode())
    for part in getattr(content, "parts", None) or []:
        text = getattr(part, "text", None)
        if text:
            digest.update(text.encode("utf-8", "ignore"))
        for attr in ("function_call", "function_response"):
            tool = getattr(part, attr, None)
            if tool is not None:
                digest.update(f"{attr}:{getattr(tool, 'id', '')}:{getattr(tool, 'name', '')}".encode())
    return digest.hexdigest()


def _fingerprint(contents: list) -> str:
    digest = hashlib.sha1()
    for content in contents:
        digest.update(_content_digest(content).encode())
    return digest.hexdigest()


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _serialize(contents: list) -> str:
    lines: list[str] = []
    for content in contents:
        role = str(getattr(content, "role", "") or "user")
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            text = getattr(part, "text", None)
            if text:
                lines.append(f"{role}: {_clip(text, _PART_TEXT_CLIP)}")
            call = getattr(part, "function_call", None)
            if call is not None:
                lines.append(
                    f"{role} called {getattr(call, 'name', '')}"
                    f"({_clip(getattr(call, 'args', '') or '', _CALL_ARGS_CLIP)})"
                )
            response = getattr(part, "function_response", None)
            if response is not None:
                lines.append(
                    f"tool {getattr(response, 'name', '')} -> "
                    f"{_clip(getattr(response, 'response', '') or '', _RESPONSE_CLIP)}"
                )
            if getattr(part, "inline_data", None) is not None:
                lines.append(f"{role}: [image]")
    text = "\n".join(lines)
    cap = max(4_000, int(settings.context_condenser_max_input_chars))
    if len(text) > cap:
        # Keep the opening (original goal) and the most recent aged-out part.
        head = text[: cap // 5]
        tail = text[-(cap - len(head)) :]
        text = f"{head}\n…[middle omitted]…\n{tail}"
    return text


async def _summarize(runtime_config: Any, previous: str, block: str) -> str | None:
    from google.adk.models.llm_request import LlmRequest

    from nexus.model_select import create_model

    model = create_model("micro", runtime_config)
    prompt_parts = []
    if previous:
        prompt_parts.append(f"EXISTING SUMMARY (merge, keep what still matters):\n{previous}")
    prompt_parts.append(f"NEWLY AGED-OUT HISTORY:\n{block}")
    request = LlmRequest(
        model=getattr(model, "model", None),
        contents=[types.Content(role="user", parts=[types.Part(text="\n\n".join(prompt_parts))])],
        config=types.GenerateContentConfig(
            system_instruction=_CONDENSER_SYSTEM,
            temperature=0.1,
        ),
    )
    chunks: list[str] = []
    async for response in model.generate_content_async(request, stream=False):
        content = getattr(response, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None) and not getattr(part, "thought", False):
                chunks.append(part.text)
    summary = "".join(chunks).strip()
    return summary or None


def _cache_key(callback_context: Any) -> str:
    session_id = ""
    try:
        invocation = getattr(callback_context, "_invocation_context", None)
        session_id = str(getattr(getattr(invocation, "session", None), "id", "") or "")
    except Exception:
        session_id = ""
    if not session_id:
        try:
            from nexus.tools._context import get_session_id

            session_id = get_session_id()
        except RuntimeError:
            session_id = ""
    agent = str(getattr(callback_context, "agent_name", "") or "agent")
    return f"{session_id or '_default'}:{agent}"


def _load_state(key: str, callback_context: Any) -> _CondensedState | None:
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    state = getattr(callback_context, "state", None)
    if state is None:
        return None
    try:
        stored = (state.get(_STATE_KEY) or {}).get(str(getattr(callback_context, "agent_name", "")))
    except Exception:
        return None
    return _CondensedState.from_dict(stored)


def _store_state(key: str, callback_context: Any, value: _CondensedState) -> None:
    with _cache_lock:
        if key not in _cache and len(_cache) >= _MAX_CACHE_ENTRIES:
            _cache.pop(next(iter(_cache)), None)
        _cache[key] = value
    state = getattr(callback_context, "state", None)
    if state is None:
        return
    try:
        # Session state survives process restarts with the Firestore session,
        # so a resumed run does not pay to re-summarize.
        stored = dict(state.get(_STATE_KEY) or {})
        stored[str(getattr(callback_context, "agent_name", ""))] = value.to_dict()
        state[_STATE_KEY] = stored
    except Exception:
        logger.debug("Could not persist condensed context to session state", exc_info=True)


def clear_condensed_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _summary_content(summary: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=CONDENSED_PREFIX + summary)])


def _split_index(contents: list, tokens: list[int], *, floor: int, keep_budget: int) -> int:
    """First index of the raw tail to keep; everything in [floor, split) ages out."""
    split = len(contents) - 1
    acc = tokens[split]
    while split - 1 >= floor and acc + tokens[split - 1] <= keep_budget:
        split -= 1
        acc += tokens[split]
    # Never start the raw tail on a tool response whose call would be summarized.
    if (
        split - 1 >= floor
        and _has_function_response(contents[split])
        and _has_function_call(contents[split - 1])
    ):
        split -= 1
    return split


def make_context_condenser(runtime_config: Any | None = None):
    """Return an async ``before_model_callback`` that condenses old history."""

    async def before_model_callback(callback_context, llm_request):
        if not (settings.context_condenser_enabled and settings.enforce_context_budget):
            return None
        contents = list(getattr(llm_request, "contents", None) or [])
        if len(contents) < 4:
            return None
        _, budget = _input_token_budget(runtime_config)
        cfg = getattr(llm_request, "config", None)
        fixed = _estimate_system_tokens(llm_request) + _estimate_tokens_for_tools(
            getattr(cfg, "tools", None) if cfg else None
        )
        tokens = [_estimate_tokens_for_content(c) for c in contents]
        key = _cache_key(callback_context)

        state = _load_state(key, callback_context)
        upto, summary = 0, ""
        if (
            state is not None
            and 0 < state.upto < len(contents)
            and _fingerprint(contents[: state.upto]) == state.fingerprint
        ):
            upto, summary = state.upto, state.summary

        trigger = budget * float(settings.context_condense_trigger_ratio)
        view_tokens = fixed + sum(tokens[upto:]) + (
            _estimate_tokens_from_text(summary) if summary else 0
        )
        if view_tokens > trigger:
            keep_budget = max(0, int(budget * float(settings.context_condense_keep_ratio)) - fixed)
            split = _split_index(contents, tokens, floor=upto, keep_budget=keep_budget)
            if split > upto:
                try:
                    new_summary = await asyncio.wait_for(
                        _summarize(runtime_config, summary, _serialize(contents[upto:split])),
                        timeout=float(settings.context_condenser_timeout_seconds),
                    )
                except Exception as exc:
                    logger.warning("Context condenser failed; trimmer will drop instead: %s", exc)
                    new_summary = None
                if new_summary:
                    logger.info(
                        "Condensed %d messages (~%d tokens) into a %d-char summary",
                        split - upto,
                        sum(tokens[upto:split]),
                        len(new_summary),
                    )
                    upto, summary = split, new_summary
                    _store_state(
                        key,
                        callback_context,
                        _CondensedState(upto, _fingerprint(contents[:upto]), summary),
                    )

        if upto and summary:
            llm_request.contents = [_summary_content(summary), *contents[upto:]]
        return None

    return before_model_callback


# ── Todo recitation ─────────────────────────────────────────────

_TODO_MARKS = {"done": "x", "in_progress": "~"}
_MAX_RECITED_ITEMS = 12


def _todo_items() -> list[dict[str, str]]:
    from nexus.tools.workspace import get_cached_todo_items

    return get_cached_todo_items()


def make_todo_reciter():
    """Return a ``before_model_callback`` that re-states open todos mid-loop."""

    def before_model_callback(callback_context, llm_request):
        if not settings.todo_recitation_enabled:
            return None
        contents = list(getattr(llm_request, "contents", None) or [])
        # Only between tool rounds; a fresh user message carries its own intent.
        if not contents or not _has_function_response(contents[-1]):
            return None
        try:
            items = _todo_items()
        except Exception:
            return None
        if not items or all(item.get("status") == "done" for item in items):
            return None
        lines = [
            f"- [{_TODO_MARKS.get(item.get('status', ''), ' ')}] {_clip(item.get('title', ''), 120)}"
            for item in items[:_MAX_RECITED_ITEMS]
        ]
        reminder = (
            "[runtime reminder, not a user message] Current plan (todo.md):\n"
            + "\n".join(lines)
        )
        llm_request.contents = [
            *contents,
            types.Content(role="user", parts=[types.Part(text=reminder)]),
        ]
        return None

    return before_model_callback


def make_context_callbacks(runtime_config: Any | None = None, *, recite_todos: bool = False) -> list:
    """Ordered ``before_model_callback`` chain: condense, trim, then recite."""
    callbacks = [make_context_condenser(runtime_config), make_context_trimmer(runtime_config)]
    if recite_todos:
        callbacks.append(make_todo_reciter())
    return callbacks


__all__ = [
    "CONDENSED_PREFIX",
    "clear_condensed_cache",
    "make_context_callbacks",
    "make_context_condenser",
    "make_todo_reciter",
]
