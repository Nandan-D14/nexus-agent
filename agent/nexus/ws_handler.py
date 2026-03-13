"""WebSocket handler — routes binary (audio) and JSON (commands) frames."""

from __future__ import annotations

import asyncio
import json
import logging

from starlette.websockets import WebSocket, WebSocketDisconnect

from nexus.orchestrator import NexusOrchestrator
from nexus.session import Session, SessionManager

logger = logging.getLogger(__name__)


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

    orchestrator = NexusOrchestrator(
        session=session,
        ws=ws,
        history_repository=session_manager.history_repository,
    )

    try:
        # Initialize voice + agent connections
        await ws.send_json({"type": "sandbox_status", "status": "connecting"})
        await orchestrator.initialize()

        # Start background task: Gemini Live → frontend
        voice_task = asyncio.create_task(orchestrator.run_voice_receive_loop())

        # Keep background tasks alive so they aren't garbage-collected
        _bg_tasks: set[asyncio.Task] = set()

        def _track(t: asyncio.Task) -> None:
            _bg_tasks.add(t)
            t.add_done_callback(_bg_tasks.discard)

        # Main loop: frontend → agent/voice
        try:
            while True:
                message = await ws.receive()

                if message.get("type") == "websocket.disconnect":
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

                    if msg_type == "text_input":
                        text = data.get("text", "").strip()
                        if text:
                            # Run as background task so stop_agent can interrupt
                            _track(asyncio.create_task(orchestrator.handle_text_input(text)))

                    elif msg_type == "analyze_screen":
                        _track(asyncio.create_task(orchestrator.handle_analyze_screen()))

                    elif msg_type == "stop_agent":
                        await orchestrator.stop_agent()

                    elif msg_type == "permission_response":
                        task_id = data.get("task_id", "")
                        approved = data.get("approved", False)
                        if task_id:
                            orchestrator.handle_permission_response(task_id, approved)

                    elif msg_type == "ping":
                        await ws.send_json({"type": "pong"})
                        session.touch()

                    else:
                        logger.debug("Unknown message type: %s", msg_type)

        except WebSocketDisconnect:
            logger.info("Client disconnected from session %s", session.id)
        finally:
            voice_task.cancel()
            try:
                await voice_task
            except asyncio.CancelledError:
                pass

    except Exception:
        logger.exception("WebSocket handler error for session %s", session.id)
        try:
            await ws.send_json({
                "type": "error",
                "code": "WS_ERROR",
                "message": "Server error. Please reconnect.",
            })
        except Exception:
            pass
    finally:
        await orchestrator.close()
        logger.info("WebSocket handler finished for session %s", session.id)
