# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Session-scoped attribute namespaces (a ``threading.local`` replacement).

Sync tools run in ``asyncio.to_thread`` pool threads while the gateway and
orchestrator read state on the event loop thread, so ``threading.local`` state
written by a tool is invisible to them, and pool-thread reuse can leak it
between sessions. ``to_thread`` copies contextvars, so keying by the current
session id resolves identically on both sides.
"""

from __future__ import annotations

import threading
from typing import Any

_DEFAULT_KEY = "_default"
_MAX_SESSIONS = 2048


def _session_key() -> str:
    from nexus.tools._context import get_session_id

    try:
        return get_session_id() or _DEFAULT_KEY
    except RuntimeError:
        return _DEFAULT_KEY


class SessionLocal:
    """Attribute namespace scoped to the current session (drop-in for ``threading.local``)."""

    _registry: list["SessionLocal"] = []

    def __init__(self) -> None:
        object.__setattr__(self, "_data", {})
        object.__setattr__(self, "_lock", threading.Lock())
        SessionLocal._registry.append(self)

    def _namespace(self) -> dict[str, Any]:
        key = _session_key()
        with self._lock:
            ns = self._data.get(key)
            if ns is None:
                if len(self._data) >= _MAX_SESSIONS:
                    # Bound memory if teardown was missed: evict the oldest session.
                    self._data.pop(next(iter(self._data)), None)
                ns = self._data[key] = {}
            return ns

    def __getattr__(self, name: str) -> Any:
        ns = self._namespace()
        try:
            return ns[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
        self._namespace()[name] = value

    def __delattr__(self, name: str) -> None:
        self._namespace().pop(name, None)

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id or _DEFAULT_KEY, None)


def clear_session_state(session_id: str) -> None:
    """Forget every session-scoped namespace entry for a session (call on teardown)."""
    for namespace in list(SessionLocal._registry):
        namespace.drop(session_id)


__all__ = ["SessionLocal", "clear_session_state"]
