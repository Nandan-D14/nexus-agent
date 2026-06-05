# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""WebSocket handler — routes binary (audio) and JSON (commands) frames."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Optional

from starlette.websockets import WebSocket, WebSocketDisconnect

from nexus.dependencies import get_production_task_repository, get_task_queue
from nexus.orchestrator import NexusOrchestrator
from nexus.production_tasks import TERMINAL_TASK_STATUSES
from nexus.runtime_config import runtime_config_snapshot
from nexus.session import Session, SessionManager

logger = logging.getLogger(__name__)


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
                self._redis = redis.from_url(settings.redis_url)
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
    last_seq = after_seq
    idle_terminal_polls = 0
    while True:
        events = await repo.list_events(
            task_id=task_id,
            owner_id=owner_id,
            after_seq=last_seq,
            run_id=run_id,
            limit=100,
        )
        for event in events:
            last_seq = max(last_seq, int(getattr(event, "seq", 0) or 0))
            delivered = await send_json(_event_to_ws_frame(event))
            if not delivered:
                return

        task = await repo.get_task(task_id)
        terminal = bool(task and task.status in TERMINAL_TASK_STATUSES)
        if terminal and not events:
            idle_terminal_polls += 1
            if idle_terminal_polls >= 2:
                return
        elif events:
            idle_terminal_polls = 0

        await asyncio.sleep(1.0)


async def _try_start_durable_text_run(
    *,
    session: Session,
    orchestrator: NexusOrchestrator,
    text: str,
    connector_ids: list[str],
    uploaded_files: list[dict[str, Any]],
    send_json,
) -> bool:
    """Create and enqueue a durable run for a WebSocket text turn.

    Returns True when durable execution owns the turn. Returns False to let the
    caller use the legacy live WebSocket path.
    """
    repo = get_production_task_repository()
    queue = get_task_queue()
    if not getattr(settings, "task_worker_enabled", False):
        return False
    is_queue_configured = getattr(queue, "is_configured", None)
    if callable(is_queue_configured) and not is_queue_configured():
        return False

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
            "uploaded_files": uploaded_files,
        },
    )

    enqueue = await queue.enqueue_task_run(task_id=task.task_id, run_id=run.run_id)
    if not enqueue.queued:
        logger.info(
            "Durable queue unavailable for session %s task %s run %s: %s",
            session.id,
            task.task_id,
            run.run_id,
            enqueue.reason,
        )
        return False

    await send_json(
        {
            "type": "run_queued",
            "task_id": task.task_id,
            "run_id": run.run_id,
            "queue": enqueue.__dict__,
        }
    )
    return True


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
                            _touch_session()
                            connector_ids = [
                                str(item).strip()
                                for item in (data.get("connector_ids") or [])
                                if str(item).strip()
                            ]
                            uploaded_files = [
                                item
                                for item in (data.get("uploaded_files") or [])
                                if isinstance(item, dict)
                            ]
                            durable_started = False
                            try:
                                durable_started = await _try_start_durable_text_run(
                                    session=session,
                                    orchestrator=orchestrator,
                                    text=text,
                                    connector_ids=connector_ids,
                                    uploaded_files=uploaded_files,
                                    send_json=_safe_send_json,
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to start durable text run for session %s; using live path.",
                                    session.id,
                                    exc_info=True,
                                )

                            if durable_started:
                                _track(
                                    asyncio.create_task(
                                        _stream_durable_task_events(
                                            repo=get_production_task_repository(),
                                            task_id=session.task_id,
                                            owner_id=session.owner_id,
                                            run_id=session.current_run_id,
                                            send_json=_safe_send_json,
                                            after_seq=0,
                                        )
                                    ),
                                    label="stream_durable_task_events",
                                )
                                continue

                            # Run as background task so stop_agent can interrupt.
                            _track(
                                asyncio.create_task(
                                    orchestrator.handle_text_input(
                                        text,
                                        connector_ids=connector_ids,
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

                    elif msg_type == "permission_response":
                        _touch_session()
                        task_id = data.get("task_id", "")
                        approved = data.get("approved", False)
                        if task_id:
                            orchestrator.handle_permission_response(task_id, approved)

                    elif msg_type == "ping":
                        await _safe_send_json({"type": "pong"})
                        if orchestrator.has_active_agent_turn() or _has_active_bg_task():
                            _touch_session()
                            try:
                                session.sandbox.extend_timeout(900)
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
            if _bg_tasks:
                await asyncio.gather(*_bg_tasks, return_exceptions=True)

    except Exception:
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
