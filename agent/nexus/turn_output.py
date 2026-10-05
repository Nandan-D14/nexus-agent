# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""One rule set for sorting model output into reasoning, narration, and answer.

Both the live event mapper (orchestrator) and the turn driver (agent.py) use
this module so a part is never "thinking" on screen but "answer" in history.

Kinds:
* ``reasoning`` -- ``part.thought`` (ADK maps provider reasoning fields to it),
  or plain text on a non-final event when ``reasoning_is_text`` is enabled.
* ``narration`` -- non-thought text in an event that also issues tool calls.
* ``answer`` -- text in a final response event. The heuristic never applies.

Answer selection (OpenClaw rule): progress narration written before later
tool work never counts as the answer. Only narration attached to the *last*
tool batch may stand in when the model ends without final text.
"""

from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Literal

PartKind = Literal["reasoning", "narration", "answer"]

_GENERIC_STUB_RE = re.compile(
    r"^\W*(?:all\s+)?(?:done|complete|completed|finished|all set|task complete[d]?)\b",
    re.IGNORECASE,
)
_STUB_MAX_CHARS = 120


def _is_thought(part: Any) -> bool:
    return bool(getattr(part, "thought", False))


def classify_text_part(
    part: Any,
    *,
    is_final: bool,
    has_function_calls: bool,
    reasoning_is_text: bool = False,
) -> PartKind:
    """Classify one text part of an ADK event."""
    if _is_thought(part):
        return "reasoning"
    if has_function_calls and not is_final:
        return "narration"
    if is_final:
        return "answer"
    return "reasoning" if reasoning_is_text else "answer"


def looks_like_generic_stub(text: str | None) -> bool:
    """Short "done" replies with no link or detail are not real answers."""
    raw = str(text or "").strip()
    if not raw or len(raw) >= _STUB_MAX_CHARS:
        return False
    if "http" in raw or "`" in raw or "/" in raw:
        return False
    return bool(_GENERIC_STUB_RE.match(raw))


def _event_function_calls(event: Any) -> list[Any]:
    getter = getattr(event, "get_function_calls", None)
    if callable(getter):
        try:
            return list(getter() or [])
        except Exception:
            pass
    parts = getattr(getattr(event, "content", None), "parts", None) or []
    return [p.function_call for p in parts if getattr(p, "function_call", None)]


def _is_final_event(event: Any) -> bool:
    checker = getattr(event, "is_final_response", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


@dataclass
class TurnOutput:
    """Accumulates the text an agent run produced, sorted by kind."""

    reasoning_is_text: bool = False
    answer: str = ""
    last_reasoning: str = ""
    completion_summary: str = ""
    tool_batches: int = 0
    # Narration attached to the most recent tool-call event; cleared when a
    # later event carries tool calls without narration.
    _last_call_narration: str = ""
    _narration_after_last_batch: bool = False
    narrations: list[str] = field(default_factory=list)

    def observe(self, event: Any) -> None:
        parts = getattr(getattr(event, "content", None), "parts", None) or []
        if not parts:
            return
        calls = _event_function_calls(event)
        is_final = _is_final_event(event)
        if any(getattr(p, "function_response", None) for p in parts):
            self.tool_batches += 1
        if calls:
            for call in calls:
                if str(getattr(call, "name", "") or "") == "report_completion":
                    args = getattr(call, "args", None) or {}
                    summary = str(args.get("summary") or "").strip() if isinstance(args, dict) else ""
                    if summary:
                        self.completion_summary = summary
        texts: dict[str, list[str]] = {"reasoning": [], "narration": [], "answer": []}
        for part in parts:
            text = getattr(part, "text", None)
            if not text:
                continue
            kind = classify_text_part(
                part,
                is_final=is_final,
                has_function_calls=bool(calls),
                reasoning_is_text=self.reasoning_is_text,
            )
            texts[kind].append(text)
        if texts["reasoning"]:
            self.last_reasoning = "".join(texts["reasoning"])
        if calls:
            narration = "".join(texts["narration"]).strip()
            self._last_call_narration = narration
            if narration:
                self.narrations.append(narration)
        if texts["answer"]:
            joined = "".join(texts["answer"]).strip()
            if joined:
                self.answer = joined

    @property
    def last_batch_narration(self) -> str:
        """Narration written alongside the final tool batch, if any."""
        return self._last_call_narration


def select_answer(
    output: TurnOutput,
    *,
    promotable: Callable[[str | None], bool],
) -> str | None:
    """Pick the user-facing answer, in priority order.

    1. Final text, unless it is a generic stub.
    2. Narration attached to the last tool batch.
    3. The ``report_completion`` summary.
    Returns None when nothing qualifies; the caller then runs one tool-free
    finalization pass.
    """
    final = output.answer
    if promotable(final) and not looks_like_generic_stub(final):
        return final
    narration = output.last_batch_narration
    if promotable(narration) and not looks_like_generic_stub(narration):
        return narration
    if promotable(output.completion_summary):
        return output.completion_summary
    if promotable(final):
        return final
    return None


# ── Tool-free finalization pass ─────────────────────────────────

_FINALIZATION_PASS: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "nexus_finalization_pass", default=False
)
# Tools that may still run during finalization: they only record the result.
FINALIZATION_ALLOWED_TOOLS = frozenset({"report_completion"})
FINALIZATION_NOTE = (
    "[runtime note, not a user message] Tools are disabled for this reply. "
    "Write the final answer to the user now from the tool results above. "
    "Do not repeat completed work. If something is unfinished, say what is "
    "done, what is left, and why."
)


@contextmanager
def finalization_pass() -> Iterator[None]:
    """Mark the enclosed agent run as the one tool-free finalization pass."""
    token = _FINALIZATION_PASS.set(True)
    try:
        yield
    finally:
        _FINALIZATION_PASS.reset(token)


def finalization_pass_active() -> bool:
    return _FINALIZATION_PASS.get()


def finalization_blocked_result(tool_name: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "summary": f"{tool_name} was not run: tools are disabled while writing the final reply.",
        "error_code": "FINALIZATION_PASS",
        "detail": {"tool": tool_name, "retryable": False},
        "metadata": {"policy_action": "deny", "reason": "finalization_pass"},
    }


def make_finalization_guard():
    """``before_model_callback`` that turns tools off for the finalization pass.

    Two layers: ``tool_choice="none"`` at the model (ADK >= 2.6 maps
    ``FunctionCallingConfig(mode=NONE)`` through LiteLLM), plus a runtime note.
    Tool declarations stay in the request so the history's tool calls remain
    valid for every provider; the gateway still blocks any call that slips
    through.
    """

    def before_model_callback(callback_context, llm_request):
        if not finalization_pass_active():
            return None
        from google.genai import types

        config = getattr(llm_request, "config", None)
        if config is not None and getattr(config, "tools", None):
            try:
                config.tool_config = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.NONE
                    )
                )
            except Exception:
                pass
        contents = list(getattr(llm_request, "contents", None) or [])
        llm_request.contents = [
            *contents,
            types.Content(role="user", parts=[types.Part(text=FINALIZATION_NOTE)]),
        ]
        return None

    return before_model_callback


__all__ = [
    "FINALIZATION_ALLOWED_TOOLS",
    "FINALIZATION_NOTE",
    "PartKind",
    "TurnOutput",
    "classify_text_part",
    "finalization_blocked_result",
    "finalization_pass",
    "finalization_pass_active",
    "looks_like_generic_stub",
    "make_finalization_guard",
    "select_answer",
]
