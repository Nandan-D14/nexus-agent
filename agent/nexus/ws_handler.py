"""WebSocket handler — routes binary (audio) and JSON (commands) frames."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict

from starlette.websockets import WebSocket, WebSocketDisconnect

from nexus.orchestrator import NexusOrchestrator
from nexus.session import Session, SessionManager

logger = logging.getLogger(__name__)


class _ActionRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        recent = [hit for hit in self._hits[key] if now - hit < self.window_seconds]
        if len(recent) >= self.max_requests:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True


action_rate_limiter = _ActionRateLimiter(max_requests=25, window_seconds=60)


async def handle_websocket(
    ws: WebSocket,
    session: Session,
    session_manager: SessionManager,
) -> None:
    """Main WebSocket handler for a connected client.

    Manages the full lifecycle:
    1. Accept connection
    2. Initialize orchestrator (voice + agent)
    3. Run voice receive loop in background
    4. Process incoming frames from browser
    5. Clean up on disconnect
    """
    await ws.accept()
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

    await _safe_send_json({"type": "sandbox_status", "status": "connecting"})

    try:
        await session_manager.activate_session(session.id)
    except Exception as exc:
        logger.exception("Failed to activate session %s", session.id)
        await _safe_send_json(
            {
                "type": "error",
                "code": "SANDBOX_INIT_ERROR",
                "message": str(exc),
            }
        )
        await ws.close(code=1011, reason="Sandbox activation failed")
        return

    orchestrator = NexusOrchestrator(
        session=session,
        ws=ws,
        history_repository=session_manager.history_repository,
    )

    try:
        # Initialize voice + agent connections
        await orchestrator.initialize()

        # Start background task: Gemini Live → frontend
        voice_task = asyncio.create_task(orchestrator.run_voice_receive_loop())

        # Keep background tasks alive so they aren't garbage-collected
        _bg_tasks: set[asyncio.Task] = set()

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
                    orchestrator.mark_ws_disconnected()
                    break

                # Binary frame = raw PCM audio from mic
                if "bytes" in message and message["bytes"]:
                    await orchestrator.handle_user_audio(message["bytes"])

                # Text frame = JSON command
                elif "text" in message and message["text"]:
                    try:
                        data = json.loads(message["text"])
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from client")
                        continue

                    msg_type = data.get("type", "")
                    if msg_type in {"text_input", "analyze_screen", "start_voice"}:
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
                            # Run as background task so stop_agent can interrupt
                            _track(
                                asyncio.create_task(orchestrator.handle_text_input(text)),
                                label="handle_text_input",
                            )

                    elif msg_type == "start_voice":
                        _track(
                            asyncio.create_task(orchestrator.start_voice()),
                            label="start_voice",
                        )

                    elif msg_type == "analyze_screen":
                        _track(
                            asyncio.create_task(orchestrator.handle_analyze_screen()),
                            label="handle_analyze_screen",
                        )

                    elif msg_type == "stop_agent":
                        await orchestrator.stop_agent()

                    elif msg_type == "permission_response":
                        task_id = data.get("task_id", "")
                        approved = data.get("approved", False)
                        if task_id:
                            orchestrator.handle_permission_response(task_id, approved)

                    elif msg_type == "ping":
                        await _safe_send_json({"type": "pong"})
                        session.touch()
                        # Keep sandbox alive on every ping from frontend
                        try:
                            session.sandbox.extend_timeout(900)
                        except Exception:
                            pass

                    else:
                        logger.debug("Unknown message type: %s", msg_type)

        except WebSocketDisconnect:
            orchestrator.mark_ws_disconnected()
            logger.info("Client disconnected from session %s", session.id)
        finally:
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
        await orchestrator.close()
        logger.info("WebSocket handler finished for session %s", session.id)
