# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Mid-run user messages (OpenClaw-style queue modes).

A message that arrives while a turn is running is handled in one of three
ways:

* ``interrupt`` -- "stop" / "cancel": abort the run (always on).
* ``followup`` (default) -- queue it as the next turn after the current one.
* ``steer`` -- deliver it to the running turn at its next model call, as a
  runtime block, without starting a new turn.
"""

from __future__ import annotations

import re
import threading

from nexus.prompt_assembly import runtime_block
from nexus.prompt_safety import escape_internal_delimiters

QUEUE_MODES = frozenset({"followup", "steer"})

_STOP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:stop|cancel|abort|halt)(?:\s+(?:it|that|this|now|the\s+task|everything))?\s*[.!]*\s*$",
    re.IGNORECASE,
)

_lock = threading.Lock()
_pending: dict[str, list[str]] = {}
# Steering already delivered this turn; re-sent on every later model call of
# the same turn (injection is per-request, not stored in session history).
_active: dict[str, list[str]] = {}
_MAX_PENDING = 5


def is_stop_command(text: str) -> bool:
    return bool(_STOP_RE.match(str(text or "")))


def push_steer(session_id: str, text: str) -> None:
    body = str(text or "").strip()
    if not session_id or not body:
        return
    with _lock:
        queue = _pending.setdefault(session_id, [])
        queue.append(body[:4000])
        del queue[:-_MAX_PENDING]


def pop_steer(session_id: str) -> list[str]:
    """Move queued steering to the active set and return everything active."""
    with _lock:
        fresh = _pending.pop(session_id, [])
        active = _active.setdefault(session_id, [])
        active.extend(fresh)
        del active[:-_MAX_PENDING]
        if not active:
            _active.pop(session_id, None)
        return list(active)


def clear_steer(session_id: str) -> None:
    """Forget steering at turn end (queued notes become the next turn)."""
    with _lock:
        _active.pop(session_id, None)


def take_pending(session_id: str) -> list[str]:
    """Steering that arrived too late for the turn; run it as a follow-up."""
    with _lock:
        return _pending.pop(session_id, [])


def make_steering_injector():
    """``before_model_callback`` that hands queued steering to the running turn."""

    def before_model_callback(callback_context, llm_request):
        from nexus.tools._context import get_session_id

        try:
            session_id = get_session_id()
        except RuntimeError:
            return None
        notes = pop_steer(session_id)
        if not notes:
            return None
        from google.genai import types

        body = "\n".join(f"- {escape_internal_delimiters(note)}" for note in notes)
        block = runtime_block(
            "directive",
            "The user sent this while you were working. Adjust the current task "
            "accordingly; do not restart finished steps:\n" + body,
        )
        contents = list(getattr(llm_request, "contents", None) or [])
        llm_request.contents = [*contents, types.Content(role="user", parts=[types.Part(text=block)])]
        return None

    return before_model_callback


__all__ = [
    "QUEUE_MODES",
    "clear_steer",
    "is_stop_command",
    "make_steering_injector",
    "pop_steer",
    "push_steer",
    "take_pending",
]
