# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Event sink abstraction — fan-out for orchestrator events.

The orchestrator currently sends agent events directly to the WebSocket
via ``_send_json``. As part of the durable-execution migration we want
those same events to be:

  1. Streamed to the live WebSocket (existing behavior)
  2. Persisted to the durable task event log so reconnecting clients can
     replay everything that happened while they were disconnected
  3. Optionally fanned out to other listeners (logs, metrics, replicas)

This module introduces a small interface so the orchestrator can stay
agnostic about *where* its events end up. It also provides composable
implementations:

  - ``WebSocketEventSink`` writes JSON frames to a WebSocket
  - ``DurableEventSink``  appends events to ``ProductionTaskRepository``
  - ``CompositeEventSink``  fans out to multiple sinks; failures in one
    sink never break another (we log and continue)
  - ``NullEventSink`` drops everything (useful for tests)

The orchestrator can keep using its existing ``_send_json`` callback in
parallel during the migration. New code should prefer ``EventSink`` so
that durable replay works automatically.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Iterable, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# A concrete WebSocket-like object only needs a ``send_json`` coroutine.
SendJsonCallback = Callable[[dict[str, Any]], Awaitable[Any]]

# Event types we never want to persist durably (too chatty / not useful
# for replay). Keep this list small and explicit.
EPHEMERAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "pong",
        "voice_status",
        "sandbox_status",  # current sandbox status is recomputed on resume
    }
)


@runtime_checkable
class EventSink(Protocol):
    """Anything that can receive an orchestrator event."""

    async def send(self, event: dict[str, Any]) -> None:  # pragma: no cover - protocol
        ...


class NullEventSink:
    """No-op sink used in tests and when no transport is available."""

    async def send(self, event: dict[str, Any]) -> None:  # noqa: D401 - simple
        return None


class WebSocketEventSink:
    """Writes events to a WebSocket via a ``send_json`` callback.

    Failures are swallowed so other sinks in a composite pipeline keep
    working. The orchestrator already has its own logic for treating a
    failed WS send as a disconnect signal; this sink does not duplicate
    that logic.
    """

    def __init__(self, send_json: SendJsonCallback) -> None:
        self._send_json = send_json

    async def send(self, event: dict[str, Any]) -> None:
        try:
            await self._send_json(event)
        except Exception:
            logger.debug(
                "WebSocketEventSink.send failed for event type=%s",
                event.get("type"),
                exc_info=True,
            )


class DurableEventSink:
    """Persists events to the durable task event log.

    The sink is bound to a (task_id, run_id, owner_id) triple and writes
    every non-ephemeral event to ``ProductionTaskRepository.append_event``.
    Persistence happens asynchronously and never raises into the caller.

    A sink with a missing ``task_id`` is effectively a no-op so that older
    code paths (sessions that haven't been migrated to durable tasks yet)
    can construct a sink without special-casing.
    """

    def __init__(
        self,
        repository,  # nexus.production_tasks.ProductionTaskRepository
        *,
        task_id: str,
        owner_id: str,
        run_id: Optional[str] = None,
        ephemeral_types: Iterable[str] = EPHEMERAL_EVENT_TYPES,
    ) -> None:
        self._repository = repository
        self._task_id = task_id
        self._owner_id = owner_id
        self._run_id = run_id
        self._ephemeral_types = frozenset(ephemeral_types)

    @property
    def is_active(self) -> bool:
        return bool(self._task_id and self._owner_id and self._repository is not None)

    def update_run_id(self, run_id: str | None) -> None:
        """Allow the orchestrator to bind a new run id when a turn starts."""
        self._run_id = run_id

    async def send(self, event: dict[str, Any]) -> None:
        if not self.is_active:
            return
        event_type = str(event.get("type") or "event")
        if event_type in self._ephemeral_types:
            return
        try:
            persisted_event = await self._repository.append_event(
                task_id=self._task_id,
                owner_id=self._owner_id,
                run_id=self._run_id,
                event_type=event_type,
                # Persist a *copy* so later mutation of the dict can't
                # accidentally rewrite history.
                payload=_normalize_payload(event),
            )
            event["task_id"] = self._task_id
            if self._run_id:
                event["run_id"] = self._run_id
            seq = getattr(persisted_event, "seq", None)
            if seq:
                event["seq"] = seq
            event_id = getattr(persisted_event, "event_id", None)
            if event_id:
                event["event_id"] = event_id
        except Exception:
            # Durable persistence is best-effort from the orchestrator's
            # perspective. If Firestore is unhappy we still want the live
            # WS stream to keep working.
            logger.warning(
                "DurableEventSink.send failed for task=%s run=%s type=%s",
                self._task_id,
                self._run_id,
                event_type,
                exc_info=True,
            )


class CompositeEventSink:
    """Fan-out sink that forwards each event to every child sink.

    Children run sequentially (not concurrently) to keep ordering
    predictable for downstream consumers and to avoid surprising the
    Firestore client with concurrent transactions on the same task.
    Exceptions from a single child are logged and ignored.
    """

    def __init__(self, sinks: Iterable[EventSink]) -> None:
        self._sinks: list[EventSink] = [sink for sink in sinks if sink is not None]

    @property
    def sinks(self) -> list[EventSink]:
        return list(self._sinks)

    def add(self, sink: EventSink) -> None:
        if sink is not None:
            self._sinks.append(sink)

    async def send(self, event: dict[str, Any]) -> None:
        for sink in self._sinks:
            try:
                await sink.send(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "CompositeEventSink child %s failed for event type=%s",
                    type(sink).__name__,
                    event.get("type"),
                    exc_info=True,
                )


def _normalize_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Strip the ``type`` field (kept separately) and shallow-copy."""
    payload: dict[str, Any] = {}
    for key, value in event.items():
        if key == "type":
            continue
        payload[key] = value
    return payload


def build_session_event_sink(
    *,
    repository,
    send_json: Optional[SendJsonCallback],
    task_id: Optional[str],
    owner_id: Optional[str],
    run_id: Optional[str] = None,
) -> CompositeEventSink:
    """Convenience factory used by the orchestrator and tests.

    Returns a composite sink that includes a WebSocket sink (when a
    ``send_json`` callback is provided) and a durable sink (when both
    ``task_id`` and ``owner_id`` are provided). Either side can be
    missing without breaking the other.
    """
    sinks: list[EventSink] = []
    if repository is not None and task_id and owner_id:
        sinks.append(
            DurableEventSink(
                repository,
                task_id=task_id,
                owner_id=owner_id,
                run_id=run_id,
            )
        )
    if send_json is not None:
        sinks.append(WebSocketEventSink(send_json))
    return CompositeEventSink(sinks)
