# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""WebSocket handler — routes binary (audio) and JSON (commands) frames."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from starlette.websockets import WebSocket, WebSocketDisconnect

from nexus.dependencies import get_production_task_repository, get_task_queue
from nexus.orchestrator import NexusOrchestrator
from nexus.production_tasks import TERMINAL_TASK_STATUSES, lease_is_live
from nexus.runtime_config import runtime_config_snapshot
from nexus.session import Session, SessionManager

logger = logging.getLogger(__name__)

class DurableEnqueueError(RuntimeError):
    """Raised when a durable run was persisted but the queue rejected it.

    Callers must not fall back to live execution for the same user turn —
    the failed run already owns the durable claim/bindings.
    """


class DurableTurnOutcome(str, Enum):
    """What the durable path decided to do with a user turn."""

    #: A run was queued; the caller should stream its durable events.
    STARTED = "started"
    #: Durable execution is off or unavailable; use the live WebSocket path.
    DECLINED = "declined"
    #: Durable owns this turn but refused it (e.g. one is already running).
    #: The client was already told why, so the caller must do nothing.
    REJECTED = "rejected"
    #: A run is already executing for this session. The new prompt was not
    #: accepted, but the caller must stream that run's events so the user sees
    #: the work that is still happening instead of a dead-end error.
    ATTACHED = "attached"


import redis
from nexus.config import settings

class _ActionRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int, name: str = "ws_action") -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._redis: Optional[redis.Redis] = None
        if settings.redis_url:
            try:
                self._redis = redis.from_url(
                    settings.redis_url,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
            except Exception:
                logger.warning("Failed to connect to Redis for _ActionRateLimiter '%s'; falling back to in-memory.", name)
        
        # Fallback
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        if self._redis:
            try:
                redis_key = f"{self.name}:{key}"
                pipe = self._redis.pipeline()
                pipe.incr(redis_key)
                pipe.expire(redis_key, self.window_seconds)
                results = pipe.execute()
                current_count = results[0]
                return current_count <= self.max_requests
            except Exception:
                logger.warning("Redis WS RateLimiter error; falling back to in-memory.", exc_info=True)

        now = time.time()
        recent = [hit for hit in self._hits[key] if now - hit < self.window_seconds]
        if len(recent) >= self.max_requests:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True


action_rate_limiter = _ActionRateLimiter(max_requests=25, window_seconds=60, name="ws_action")


def _event_to_ws_frame(event) -> dict[str, Any]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    frame = dict(payload)
    frame.update(
        {
            "type": event.event_type,
            "event_id": event.event_id,
            "task_id": event.task_id,
            "run_id": event.run_id,
            "seq": event.seq,
        }
    )
    return frame


async def _stream_durable_task_events(
    *,
    repo,
    task_id: str,
    owner_id: str,
    run_id: str,
    send_json,
    after_seq: int = 0,
) -> None:
    """Poll the durable event log and fan out events to a live client.

    Never raises: this coroutine is registered as a background task, and any
    exception it lets escape shows up in the UI as a scary "server error"
    frame. Firestore transient failures (missing composite index, timeouts,
    network blips) should degrade to a longer sleep, not a crash.
    """
    last_seq = after_seq
    idle_terminal_polls = 0
    consecutive_errors = 0
    while True:
        try:
            events = await repo.list_events(
                task_id=task_id,
                owner_id=owner_id,
                after_seq=last_seq,
                run_id=run_id,
                limit=100,
            )
        except Exception:
            consecutive_errors += 1
            logger.warning(
                "Durable event poll failed for task %s (attempt %d)",
                task_id,
                consecutive_errors,
                exc_info=True,
            )
            if consecutive_errors >= 20:
                logger.error(
                    "Giving up on durable event stream for task %s after repeated failures",
                    task_id,
                )
                return
            await asyncio.sleep(min(2 ** consecutive_errors, 30))
            continue

        consecutive_errors = 0
        for event in events:
            last_seq = max(last_seq, int(getattr(event, "seq", 0) or 0))
            try:
                delivered = await send_json(_event_to_ws_frame(event))
            except Exception:
                logger.debug("send_json failed while streaming durable events", exc_info=True)
                return
            if not delivered:
                return

        try:
            task = await repo.get_task(task_id)
        except Exception:
            logger.debug("Durable get_task failed while polling", exc_info=True)
            task = None
        terminal = bool(task and task.status in TERMINAL_TASK_STATUSES)
        if terminal and not events:
            idle_terminal_polls += 1
            if idle_terminal_polls >= 2:
                return
        elif events:
            idle_terminal_polls = 0

        await asyncio.sleep(1.0)


def _run_age_seconds(run) -> float | None:
    """Seconds since the run last changed, or None when it has no timestamp."""
    started = getattr(run, "updated_at", None) or getattr(run, "created_at", None)
    if started is None:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds()


def _abandoned_run_reason(run, *, cancel_requested: bool) -> tuple[str, str] | None:
    """Classify a non-terminal run nothing will ever progress.

    Returns ``(error_code, message)`` when the run must be settled so the
    session becomes usable, otherwise ``None``.

    Each branch here exists because some other recovery path cannot cover it:

    * ``queued`` — the stale-run sweeper only looks at ``running`` runs, so an
      enqueue that never reached a worker stays queued forever.
    * ``running`` with an expired lease — the sweeper *should* own this, but it
      silently does nothing when its Firestore composite index is missing, and it
      cannot make progress at all once ``cancelRequested`` is set (``requeue_run``
      refuses, so ``attempt`` never reaches the fail threshold).
    * ``cancelling`` — set by the stop button. When no worker held the run there
      is nothing left to observe the flag and finish the run.
    * ``waiting_approval`` — the approval expires client- and server-side, after
      which no one can resolve it.

    A live lease always wins: that means a worker genuinely owns the run.
    """
    status = str(getattr(run, "status", "") or "")
    if status in TERMINAL_TASK_STATUSES:
        return None
    if lease_is_live(getattr(run, "lease_expires_at", None)):
        return None

    age = _run_age_seconds(run)
    if age is None:
        return None

    grace = max(60.0, float(settings.abandoned_run_grace_seconds))
    approval_grace = max(grace, float(settings.abandoned_approval_grace_seconds))

    if status == "queued":
        if cancel_requested:
            return (
                "RUN_CANCELLED_UNCLAIMED",
                "This request was cancelled before a worker picked it up.",
            )
        if age > grace:
            return (
                "RUN_ABANDONED",
                "This request was never picked up by a worker. Please send it again.",
            )
        return None

    if status == "cancelling":
        # Stop was pressed. Give a live worker a short window to honor it, then
        # settle so `cancelRequested` stops blocking every later prompt.
        if age > min(grace, 120.0):
            return (
                "RUN_CANCEL_ORPHANED",
                "The previous request was stopped and is no longer running.",
            )
        return None

    if status == "running" and age > grace:
        return (
            "RUN_LEASE_LOST",
            "The worker running this request stopped responding. Please send it again.",
        )

    if status == "waiting_approval" and age > approval_grace:
        return (
            "APPROVAL_EXPIRED",
            "The approval request expired, so this run was closed. Please send it again.",
        )

    return None


async def _settle_abandoned_run(
    repo,
    *,
    session: Session,
    task_id: str,
    run_id: str,
    error_code: str,
    reason: str,
) -> None:
    """Fail an abandoned run and emit a terminal event. Never raises.

    The terminal event matters as much as the status: a client waiting on this
    run has no other way to learn it is over, and would keep showing a thinking
    indicator indefinitely.
    """
    logger.warning(
        "Settling abandoned durable run %s/%s (%s) so session %s is usable",
        task_id,
        run_id,
        error_code,
        session.id,
    )
    try:
        await repo.finish_run(
            task_id=task_id,
            run_id=run_id,
            status="failed",
            summary=reason,
            error=reason,
        )
        await repo.append_event(
            task_id=task_id,
            owner_id=session.owner_id,
            run_id=run_id,
            event_type="worker_failed",
            payload={"reason": reason, "error_code": error_code},
        )
    except Exception:
        logger.warning(
            "Failed to settle abandoned durable run %s/%s",
            task_id,
            run_id,
            exc_info=True,
        )


async def _clear_stuck_cancel_request(repo, *, session: Session, task_id: str) -> None:
    """Drop a ``cancelRequested`` flag that has outlived its run.

    ``request_cancel`` sets the flag on the *task*, and nothing clears it. Once
    the run it targeted is terminal the flag only does damage: ``claim_run`` and
    ``requeue_run`` both refuse outright while it is set, so every future run on
    the task is unclaimable and the session is permanently dead.
    """
    clear_cancel = getattr(repo, "clear_cancel_request", None)
    if not callable(clear_cancel):
        return
    try:
        await clear_cancel(task_id=task_id, owner_id=session.owner_id)
    except Exception:
        logger.warning(
            "Failed to clear stale cancel request on task %s",
            task_id,
            exc_info=True,
        )


async def _find_inflight_durable_run(session: Session) -> tuple[str, str] | None:
    """Return ``(task_id, run_id)`` for a durable run still executing, if any.

    This is what makes a refresh survivable: the worker owns the run, so a new
    socket only has to find it and re-attach to its event log.

    It is also the only recovery path a connecting client can rely on, so it
    settles runs that nothing is progressing (see
    :func:`_abandoned_run_reason`) instead of reporting them as in-flight
    forever.
    """
    task_id = getattr(session, "task_id", None)
    if not isinstance(task_id, str) or not task_id.startswith("task_"):
        return None

    repo = get_production_task_repository()
    try:
        task = await repo.get_task(task_id)
    except Exception:
        logger.warning("Failed to load durable task %s on reconnect", task_id, exc_info=True)
        return None
    if task is None or getattr(task, "owner_id", None) != session.owner_id:
        return None

    cancel_requested = bool(getattr(task, "cancel_requested", False))
    run_id = getattr(task, "current_run_id", None) or getattr(
        session, "current_run_id", None
    )
    if not isinstance(run_id, str) or not run_id:
        if cancel_requested:
            await _clear_stuck_cancel_request(repo, session=session, task_id=task_id)
        return None

    try:
        run = await repo.get_run(
            task_id=task_id, run_id=run_id, owner_id=session.owner_id
        )
    except Exception:
        logger.warning(
            "Failed to load durable run %s/%s on reconnect", task_id, run_id, exc_info=True
        )
        return None
    if run is None or getattr(run, "status", None) in TERMINAL_TASK_STATUSES:
        # The run is over, so a lingering cancel flag can only block new work.
        if cancel_requested:
            await _clear_stuck_cancel_request(repo, session=session, task_id=task_id)
        return None

    abandoned = _abandoned_run_reason(run, cancel_requested=cancel_requested)
    if abandoned is not None:
        error_code, reason = abandoned
        await _settle_abandoned_run(
            repo,
            session=session,
            task_id=task_id,
            run_id=run_id,
            error_code=error_code,
            reason=reason,
        )
        if cancel_requested:
            await _clear_stuck_cancel_request(repo, session=session, task_id=task_id)
        return None

    return task_id, run_id


async def _durable_run_status(repo, session: Session, task_id: str, run_id: str) -> str:
    try:
        run = await repo.get_run(
            task_id=task_id, run_id=run_id, owner_id=session.owner_id
        )
    except Exception:
        logger.warning(
            "Failed to load durable run status %s/%s", task_id, run_id, exc_info=True
        )
        return ""
    return str(getattr(run, "status", "") or "") if run is not None else ""


async def _supersede_paused_durable_run(
    repo,
    *,
    session: Session,
    task_id: str,
    run_id: str,
) -> bool:
    """Finish a paused run so a new prompt can start. Returns False on failure."""
    reason = "Superseded by a new message."
    try:
        await repo.finish_run(
            task_id=task_id,
            run_id=run_id,
            status="cancelled",
            summary=reason,
            error=reason,
        )
        await repo.append_event(
            task_id=task_id,
            owner_id=session.owner_id,
            run_id=run_id,
            event_type="worker_failed",
            payload={"reason": reason, "error_code": "RUN_SUPERSEDED"},
        )
        logger.info(
            "Superseded paused durable run %s/%s for session %s",
            task_id,
            run_id,
            session.id,
        )
        return True
    except Exception:
        logger.warning(
            "Failed to supersede paused durable run %s/%s",
            task_id,
            run_id,
            exc_info=True,
        )
        return False


async def _stop_durable_run(*, session: Session, task_id: str, send_json) -> None:
    """Honor the stop button for a durable run, and never leave it wedged.

    ``request_cancel`` only raises a flag on the task; some live worker has to
    observe it and finish the run. When no worker holds a live lease nothing ever
    will, and the flag then blocks ``claim_run``/``requeue_run`` for every future
    run on the task — so the session would be permanently unusable. In that case
    settle the run here and release the flag.
    """
    repo = get_production_task_repository()
    try:
        cancelled = await repo.request_cancel(
            task_id=task_id, owner_id=session.owner_id
        )
    except Exception:
        logger.warning(
            "Failed to request durable cancel for task %s", task_id, exc_info=True
        )
        return
    if not cancelled:
        return

    try:
        task = await repo.get_task(task_id)
        run_id = getattr(task, "current_run_id", None) if task else None
        run = (
            await repo.get_run(
                task_id=task_id, run_id=run_id, owner_id=session.owner_id
            )
            if isinstance(run_id, str) and run_id
            else None
        )
    except Exception:
        logger.warning(
            "Failed to inspect durable run while stopping task %s",
            task_id,
            exc_info=True,
        )
        return

    if run is None:
        await _clear_stuck_cancel_request(repo, session=session, task_id=task_id)
        return
    if str(getattr(run, "status", "") or "") in TERMINAL_TASK_STATUSES:
        await _clear_stuck_cancel_request(repo, session=session, task_id=task_id)
        return
    if lease_is_live(getattr(run, "lease_expires_at", None)):
        # A worker owns this run and its cancel watcher will finish it.
        return

    reason = "Stopped by user."
    await _settle_abandoned_run(
        repo,
        session=session,
        task_id=task_id,
        run_id=str(run_id),
        error_code="RUN_STOPPED_BY_USER",
        reason=reason,
    )
    await _clear_stuck_cancel_request(repo, session=session, task_id=task_id)
    await send_json(
        {
            "type": "worker_finished",
            "task_id": task_id,
            "run_id": run_id,
            "status": "cancelled",
            "summary": reason,
        }
    )


async def _report_busy_durable_run(
    *,
    session: Session,
    task_id: str,
    run_id: str,
    status: str,
    pending_text: str | None = None,
    send_json,
) -> DurableTurnOutcome:
    """Tell the client a run is already in flight and stream it instead.

    The old behavior was a bare ``error`` frame, which left the user with no way
    to see the work that was still happening — the composer unlocked, the chat
    went quiet, and every retry produced the same error. Returning ATTACHED lets
    the caller re-attach to the live event log so the run's progress shows up in
    the UI as it happens.
    """
    logger.info(
        "Attaching session %s to its in-flight run %s (%s) instead of starting a new turn",
        session.id,
        run_id,
        status or "unknown",
    )
    frame: dict[str, object] = {
        "type": "run_busy",
        "code": "RUN_IN_PROGRESS",
        "message": (
            "This session is still working on the previous request. "
            "Live progress is shown below — press stop to interrupt it."
        ),
        "task_id": task_id,
        "run_id": run_id,
        "run_status": status,
    }
    if isinstance(pending_text, str) and pending_text.strip():
        frame["pending_text"] = pending_text[:4000]
    await send_json(frame)
    return DurableTurnOutcome.ATTACHED


async def _try_start_durable_text_run(
    *,
    session: Session,
    orchestrator: NexusOrchestrator,
    text: str,
    connector_ids: list[str],
    tool_ids: list[str],
    uploaded_files: list[dict[str, Any]],
    send_json,
) -> DurableTurnOutcome:
    """Create and enqueue a durable run for a WebSocket text turn."""
    repo = get_production_task_repository()
    queue = get_task_queue()
    is_queue_configured = getattr(queue, "is_configured", None)
    queue_configured = bool(is_queue_configured()) if callable(is_queue_configured) else True

    if not getattr(settings, "task_worker_enabled", False):
        logger.debug("Durable execution skipped for %s: worker disabled", session.id)
        return DurableTurnOutcome.DECLINED
    if not queue_configured:
        logger.debug("Durable execution skipped for %s: queue unavailable", session.id)
        return DurableTurnOutcome.DECLINED

    # One run per task at a time. `create_run` repoints `currentRunId` and would
    # happily enqueue a second worker against the same session, so without this
    # guard a follow-up prompt starts a competing agent on the same sandbox.
    inflight = await _find_inflight_durable_run(session)
    if inflight:
        inflight_task_id, inflight_run_id = inflight
        inflight_status = await _durable_run_status(
            repo, session, inflight_task_id, inflight_run_id
        )
        if inflight_status == "paused":
            superseded = await _supersede_paused_durable_run(
                repo,
                session=session,
                task_id=inflight_task_id,
                run_id=inflight_run_id,
            )
            if not superseded:
                return await _report_busy_durable_run(
                    session=session,
                    task_id=inflight_task_id,
                    run_id=inflight_run_id,
                    status=inflight_status,
                    pending_text=text,
                    send_json=send_json,
                )
        else:
            # Durable execution owns the turn: do not let the live path start a
            # duplicate agent alongside the worker. Attach to the running one so
            # its progress is visible rather than leaving the user in the dark.
            if hasattr(orchestrator, "bind_durable_run"):
                try:
                    orchestrator.bind_durable_run(
                        task_id=inflight_task_id, run_id=inflight_run_id
                    )
                except Exception:
                    logger.warning(
                        "Failed to bind session %s to in-flight run %s",
                        session.id,
                        inflight_run_id,
                        exc_info=True,
                    )
            session.current_run_id = inflight_run_id
            return await _report_busy_durable_run(
                session=session,
                task_id=inflight_task_id,
                run_id=inflight_run_id,
                status=inflight_status,
                pending_text=text,
                send_json=send_json,
            )

    task_id = getattr(session, "task_id", None)
    task = None

    if isinstance(task_id, str) and task_id.startswith("task_"):
        task = await repo.get_task(task_id)
        if not task or task.owner_id != session.owner_id:
            task = None

    if task is None:
        task = await repo.create_task(
            owner_id=session.owner_id,
            title=text[:120] or "New task",
            input_text=text,
            session_id=session.id,
            metadata={"source": "websocket"},
        )
        session.task_id = task.task_id

    run = await repo.create_run(
        task_id=task.task_id,
        owner_id=session.owner_id,
        session_id=session.id,
        input_text=text,
        connector_ids=connector_ids,
        tool_ids=tool_ids,
        uploaded_files=uploaded_files,
        runtime_config_snapshot=runtime_config_snapshot(getattr(session, "runtime_config", None)),
        autonomy_mode=getattr(getattr(session, "runtime_config", None), "autonomy_mode", None),
        metadata={"source": "websocket", "user_transcript_recorded": True},
    )
    session.current_run_id = run.run_id
    if hasattr(orchestrator, "bind_durable_run"):
        orchestrator.bind_durable_run(task_id=task.task_id, run_id=run.run_id)

    await repo.append_event(
        task_id=task.task_id,
        owner_id=session.owner_id,
        run_id=run.run_id,
        event_type="transcript",
        payload={
            "role": "user",
            "text": text,
            "connector_ids": connector_ids,
            "tool_ids": tool_ids,
            "uploaded_files": uploaded_files,
        },
    )

    # Persist the user turn into session history so it survives a page refresh.
    # The durable event log above drives the live view, but the
    # /api/v1/history/{session}/messages endpoint (used on reload) reads only
    # session messages. We record it once here at enqueue; the run metadata
    # `user_transcript_recorded=True` makes the worker skip re-persisting it,
    # so there is exactly one user row and no duplicate.
    history_repository = getattr(orchestrator, "history_repository", None)
    if history_repository is not None:
        try:
            await history_repository.append_message(
                session_id=session.id,
                owner_id=session.owner_id,
                role="user",
                source="typed",
                text=text,
                attachments=uploaded_files,
            )
        except Exception:
            logger.warning(
                "Failed to persist user transcript to session history for %s",
                session.id,
                exc_info=True,
            )

    enqueue_kwargs = {"task_id": task.task_id, "run_id": run.run_id}
    claim_token = getattr(run, "claim_token", None)
    if claim_token:
        enqueue_kwargs["claim_token"] = claim_token
    enqueue = await queue.enqueue_task_run(**enqueue_kwargs)
    if not enqueue.queued:
        reason = (
            str(getattr(enqueue, "reason", "") or "").strip()
            or "Durable queue rejected the run."
        )
        logger.info(
            "Durable queue unavailable for session %s task %s run %s: %s",
            session.id,
            task.task_id,
            run.run_id,
            reason,
        )
        try:
            await repo.finish_run(
                task_id=task.task_id,
                run_id=run.run_id,
                status="failed",
                summary=reason,
                error=reason,
            )
            await repo.append_event(
                task_id=task.task_id,
                owner_id=session.owner_id,
                run_id=run.run_id,
                event_type="enqueue_rejected",
                payload={
                    "provider": getattr(enqueue, "provider", ""),
                    "reason": reason,
                },
            )
        except Exception:
            logger.warning(
                "Failed to mark durable run %s/%s failed after enqueue rejection",
                task.task_id,
                run.run_id,
                exc_info=True,
            )
        # Keep the durable task id, but clear the failed run binding so the
        # live fallback cannot execute against the rejected claim generation.
        session.current_run_id = None
        if hasattr(orchestrator, "bind_durable_run"):
            try:
                orchestrator.bind_durable_run(task_id=None, run_id=None)
            except TypeError:
                # Older orchestrators only accept keyword task/run ids.
                pass
        await send_json(
            {
                "type": "error",
                "code": "DURABLE_ENQUEUE_FAILED",
                "message": reason,
                "task_id": task.task_id,
                "run_id": run.run_id,
            }
        )
        # Do not fall through to live execution with duplicate bindings.
        raise DurableEnqueueError(reason)

    await send_json(
        {
            "type": "run_queued",
            "task_id": task.task_id,
            "run_id": run.run_id,
            "queue": enqueue.__dict__,
        }
    )
    # #region agent log
    try:
        import json as _dbg_json
        from pathlib import Path as _DbgPath
        _DbgPath(r"C:\Users\nanda\OneDrive\Desktop\co-computer\debug-2a93a8.log").open("a", encoding="utf-8").write(_dbg_json.dumps({"sessionId":"2a93a8","hypothesisId":"C","location":"ws_handler.py:run_queued","message":"durable run queued","data":{"task_id":task.task_id,"run_id":run.run_id,"provider":getattr(enqueue,"provider",None),"queued":getattr(enqueue,"queued",None)},"timestamp":int(__import__("time").time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    logger.info(
        "Durable run queued for session %s task %s run %s via %s",
        session.id,
        task.task_id,
        run.run_id,
        enqueue.provider,
    )
    return DurableTurnOutcome.STARTED


async def handle_websocket(
    ws: WebSocket,
    session: Session,
    session_manager: SessionManager,
    subprotocol: str | None = None,
) -> None:
    """Main WebSocket handler for a connected client.

    Manages the full lifecycle:
    1. Accept connection
    2. Initialize orchestrator (voice + agent)
    3. Run voice receive loop in background
    4. Process incoming frames from browser
    5. Clean up on disconnect
    """
    await ws.accept(subprotocol=subprotocol)

    send_lock = asyncio.Lock()
    setattr(ws, "_cocomputer_send_lock", send_lock)

    async def _safe_send_json(data: dict) -> bool:
        try:
            async with send_lock:
                await ws.send_json(data)
            return True
        except Exception:
            logger.warning(
                "Failed to send WS handler message: %s",
                data.get("type"),
                exc_info=True,
            )
            return False

    session_manager.cancel_idle_pause(session.id)

    async def _activate_sandbox() -> None:
        await session_manager.activate_session(session.id)

    orchestrator = NexusOrchestrator(
        session=session,
        ws=ws,
        history_repository=session_manager.history_repository,
        production_task_repository=get_production_task_repository(),
        ensure_sandbox_ready=_activate_sandbox,
    )

    had_active_agent_turn_on_disconnect = False

    def _touch_session() -> None:
        touch = getattr(session, "touch", None)
        if callable(touch):
            touch()

    try:
        # Initialize voice + agent connections
        await orchestrator.initialize(lazy_sandbox=True)


        # Start background task: Gemini Live → frontend
        voice_task = asyncio.create_task(orchestrator.run_voice_receive_loop())

        # Keep background tasks alive so they aren't garbage-collected
        _bg_tasks: set[asyncio.Task] = set()

        def _has_active_bg_task() -> bool:
            return any(not task.done() for task in _bg_tasks)

        def _surface_task_exception(task: asyncio.Task, *, label: str) -> None:
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                return

            if exc is None:
                return

            logger.error("%s failed for session %s", label, session.id, exc_info=exc)

            async def _notify() -> None:
                try:
                    await _safe_send_json(
                        {
                            "type": "error",
                            "code": "BACKGROUND_TASK_ERROR",
                            "message": f"{label} failed: {exc}",
                        }
                    )
                except Exception:
                    logger.debug(
                        "Failed to surface background task error for session %s",
                        session.id,
                        exc_info=True,
                    )

            asyncio.create_task(_notify())

        def _track(t: asyncio.Task, *, label: str) -> None:
            _bg_tasks.add(t)
            t.add_done_callback(_bg_tasks.discard)
            t.add_done_callback(lambda task: _surface_task_exception(task, label=label))

        # Run ids this socket already has a durable event stream for. Streaming
        # the same run twice would double every frame the user sees.
        _streamed_run_ids: set[str] = set()

        def _stream_durable_run(
            *,
            task_id: str,
            run_id: str,
            label: str,
            after_seq: int = 0,
        ) -> None:
            if not task_id or not run_id or run_id in _streamed_run_ids:
                return
            _streamed_run_ids.add(run_id)

            async def _stream() -> None:
                try:
                    await _stream_durable_task_events(
                        repo=get_production_task_repository(),
                        task_id=task_id,
                        owner_id=session.owner_id,
                        run_id=run_id,
                        send_json=_safe_send_json,
                        after_seq=after_seq,
                    )
                finally:
                    _streamed_run_ids.discard(run_id)

            _track(asyncio.create_task(_stream()), label=label)

        # Re-attach to a durable run that is still executing. The worker kept
        # going while the browser was away, so the only thing this socket has to
        # do is resume streaming its event log. The client hydrates events up to
        # `after_seq` on load and dedupes by event id, so overlap is harmless.
        # Best effort: a durable lookup failure here must not stop the client
        # from connecting, so it degrades to "no re-attach" instead of raising.
        try:
            inflight = await _find_inflight_durable_run(session)
        except Exception:
            logger.warning(
                "Durable re-attach lookup failed for session %s", session.id, exc_info=True
            )
            inflight = None

        if inflight:
            reattach_task_id, reattach_run_id = inflight
            logger.info(
                "Re-attaching session %s to in-flight durable run %s/%s",
                session.id,
                reattach_task_id,
                reattach_run_id,
            )
            orchestrator.bind_durable_run(
                task_id=reattach_task_id, run_id=reattach_run_id
            )
            await _safe_send_json(
                {
                    "type": "worker_claimed",
                    "task_id": reattach_task_id,
                    "run_id": reattach_run_id,
                    "reattached": True,
                }
            )
            _stream_durable_run(
                task_id=reattach_task_id,
                run_id=reattach_run_id,
                label="reattach_durable_task_events",
            )

        # Main loop: frontend → agent/voice
        try:
            while True:
                message = await ws.receive()

                if message.get("type") == "websocket.disconnect":
                    had_active_agent_turn_on_disconnect = (
                        orchestrator.has_active_agent_turn() or _has_active_bg_task()
                    )
                    orchestrator.mark_ws_disconnected()
                    break

                # Binary frame = raw PCM audio from mic
                if "bytes" in message and message["bytes"]:
                    _touch_session()
                    await orchestrator.handle_user_audio(message["bytes"])

                # Text frame = JSON command
                elif "text" in message and message["text"]:
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from client")
                        continue

                    msg_type = data.get("type", "")
                    if msg_type in {"text_input", "analyze_screen", "start_voice", "start_desktop"}:
                        if not action_rate_limiter.is_allowed(session.owner_id):
                            await _safe_send_json(
                                {
                                    "type": "error",
                                    "code": "RATE_LIMITED",
                                    "message": "Too many actions in a short period. Please wait a moment.",
                                }
                            )
                            continue

                    if msg_type == "text_input":
                        text = data.get("text", "").strip()
                        if text:
                            # Idempotency: drop an identical resubmission of the
                            # same turn (WS reconnect replay, durable+live overlap)
                            # within a short window. State lives on the session so
                            # it survives reconnects (a new handler instance).
                            _dupe_window = settings.duplicate_turn_window_seconds
                            if _dupe_window > 0:
                                _sig = hashlib.sha256(
                                    f"{session.id}\x00{text}".encode("utf-8")
                                ).hexdigest()
                                _now = time.monotonic()
                                _last_sig = getattr(session, "_last_turn_signature", None)
                                _last_at = float(getattr(session, "_last_turn_at", 0.0) or 0.0)
                                if _sig == _last_sig and (_now - _last_at) < _dupe_window:
                                    logger.info(
                                        "Dropping duplicate text_input for session %s (idempotency window)",
                                        session.id,
                                    )
                                    continue
                                session._last_turn_signature = _sig
                                session._last_turn_at = _now
                            _touch_session()
                            connector_ids = [
                                str(item).strip()
                                for item in (data.get("connector_ids") or [])
                                if str(item).strip()
                            ]
                            tool_ids = [
                                str(item).strip()
                                for item in (data.get("tool_ids") or [])
                                if str(item).strip()
                            ]
                            uploaded_files = [
                                item
                                for item in (data.get("uploaded_files") or [])
                                if isinstance(item, dict)
                            ]
                            durable = DurableTurnOutcome.DECLINED
                            try:
                                durable = await _try_start_durable_text_run(
                                    session=session,
                                    orchestrator=orchestrator,
                                    text=text,
                                    connector_ids=connector_ids,
                                    tool_ids=tool_ids,
                                    uploaded_files=uploaded_files,
                                    send_json=_safe_send_json,
                                )
                            except DurableEnqueueError:
                                logger.warning(
                                    "Durable enqueue failed for session %s; not falling back to live execution.",
                                    session.id,
                                    exc_info=True,
                                )
                                continue
                            except Exception:
                                logger.warning(
                                    "Failed to start durable text run for session %s; using live path.",
                                    session.id,
                                    exc_info=True,
                                )

                            if durable is DurableTurnOutcome.REJECTED:
                                # The client already has an explanatory error frame.
                                continue

                            if durable in {
                                DurableTurnOutcome.STARTED,
                                DurableTurnOutcome.ATTACHED,
                            }:
                                # ATTACHED means the prompt was not accepted but a
                                # run is still executing; stream it so the user can
                                # watch the work instead of staring at an error.
                                _stream_durable_run(
                                    task_id=session.task_id,
                                    run_id=session.current_run_id,
                                    label="stream_durable_task_events",
                                )
                                continue

                            # Run as background task so stop_agent can interrupt.
                            _track(
                                asyncio.create_task(
                                    orchestrator.handle_text_input(
                                        text,
                                        connector_ids=connector_ids,
                                        tool_ids=tool_ids,
                                        uploaded_files=uploaded_files,
                                    )
                                ),
                                label="handle_text_input",
                            )

                    elif msg_type == "start_voice":
                        _touch_session()
                        _track(
                            asyncio.create_task(orchestrator.start_voice()),
                            label="start_voice",
                        )

                    elif msg_type == "start_desktop":
                        _touch_session()
                        _track(
                            asyncio.create_task(orchestrator.start_desktop()),
                            label="start_desktop",
                        )

                    elif msg_type == "analyze_screen":
                        _touch_session()
                        _track(
                            asyncio.create_task(orchestrator.handle_analyze_screen()),
                            label="handle_analyze_screen",
                        )

                    elif msg_type == "stop_agent":
                        _touch_session()
                        await orchestrator.stop_agent()
                        # Durable runs execute on a detached worker; cancelling
                        # the live orchestrator is not enough to stop them.
                        durable_task_id = getattr(session, "task_id", None)
                        if isinstance(durable_task_id, str) and durable_task_id.startswith("task_"):
                            await _stop_durable_run(
                                session=session,
                                task_id=durable_task_id,
                                send_json=_safe_send_json,
                            )

                    elif msg_type == "permission_response":
                        _touch_session()
                        task_id = data.get("task_id", "")
                        approved = data.get("approved", False)
                        if task_id:
                            durable_task_id = str(
                                data.get("durable_task_id")
                                or getattr(session, "task_id", "")
                                or ""
                            )
                            if (
                                str(task_id).startswith("appr_")
                                and durable_task_id.startswith("task_")
                            ):
                                try:
                                    await get_production_task_repository().resolve_approval(
                                        task_id=durable_task_id,
                                        approval_id=str(task_id),
                                        owner_id=session.owner_id,
                                        approved=bool(approved),
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed to resolve durable approval %s",
                                        task_id,
                                        exc_info=True,
                                    )
                            else:
                                orchestrator.handle_permission_response(
                                    task_id,
                                    approved,
                                )

                    elif msg_type == "user_question_response":
                        _touch_session()
                        question_id = data.get("question_id", "")
                        answer = data.get("answer", "")
                        if question_id:
                            orchestrator.handle_user_question_response(question_id, answer)
                            # Mirror the answer into the durable event log so a
                            # detached worker run can pick it up (its ask_user
                            # future lives in another orchestrator instance).
                            durable_task_id = getattr(session, "task_id", None)
                            if isinstance(durable_task_id, str) and durable_task_id.startswith("task_"):
                                try:
                                    await get_production_task_repository().append_event(
                                        task_id=durable_task_id,
                                        owner_id=session.owner_id,
                                        run_id=getattr(session, "current_run_id", None),
                                        event_type="user_question_response",
                                        payload={
                                            "question_id": str(question_id),
                                            "answer": str(answer or ""),
                                        },
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed to persist durable question answer for task %s",
                                        durable_task_id,
                                        exc_info=True,
                                    )

                    elif msg_type == "ping":
                        await _safe_send_json({"type": "pong"})
                        if orchestrator.has_active_agent_turn() or _has_active_bg_task():
                            _touch_session()
                            try:
                                session.sandbox.extend_timeout()
                            except Exception:
                                pass

                    else:
                        logger.debug("Unknown message type: %s", msg_type)

        except WebSocketDisconnect:
            had_active_agent_turn_on_disconnect = (
                orchestrator.has_active_agent_turn() or _has_active_bg_task()
            )
            orchestrator.mark_ws_disconnected()
            logger.info("Client disconnected from session %s", session.id)
        finally:
            had_active_agent_turn_on_disconnect = (
                had_active_agent_turn_on_disconnect
                or orchestrator.has_active_agent_turn()
                or _has_active_bg_task()
            )
            orchestrator.mark_ws_disconnected()
            voice_task.cancel()
            for task in list(_bg_tasks):
                task.cancel()
            try:
                await voice_task
            except asyncio.CancelledError:
                pass
            except Exception:
                # A failed voice loop must not become "Server error. Please
                # reconnect." on the way out — that frame has no event id, so
                # the client appends a new chat row on every reconnect.
                logger.debug(
                    "Voice receive loop ended with an error during WS cleanup for session %s",
                    session.id,
                    exc_info=True,
                )
            if _bg_tasks:
                await asyncio.gather(*_bg_tasks, return_exceptions=True)

    except Exception as exc:
        logger.exception("WebSocket handler error for session %s", session.id)

        try:
            await _safe_send_json({
                "type": "error",
                "code": "WS_ERROR",
                "message": "Server error. Please reconnect.",
            })
        except Exception:
            pass
    finally:
        if not had_active_agent_turn_on_disconnect and not orchestrator.has_active_agent_turn():
            try:
                session_manager.schedule_idle_pause(session.id)
                logger.info(
                    "Scheduled idle sandbox pause after WebSocket disconnect for session %s",
                    session.id,
                )
            except Exception:
                logger.warning(
                    "Failed to schedule idle sandbox pause after WebSocket disconnect for session %s",
                    session.id,
                    exc_info=True,
                )
        await orchestrator.close()
        logger.info("WebSocket handler finished for session %s", session.id)
