"""Orchestrator — wires voice → agent → sandbox → vision → response."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from starlette.websockets import WebSocket

from nexus.agent import create_agent, create_runner, run_agent_turn
from nexus.history_repository import FirestoreHistoryRepository
from nexus.tools._context import set_sandbox
from nexus.voice import GeminiLiveManager
from nexus.prompts.system import SYSTEM_PROMPT

if TYPE_CHECKING:
    from nexus.session import Session

logger = logging.getLogger(__name__)


class NexusOrchestrator:
    """Coordinates the full voice → think → act → see loop for one session."""

    def __init__(
        self,
        session: "Session",
        ws: WebSocket,
        history_repository: FirestoreHistoryRepository | None = None,
    ) -> None:
        self.session = session
        self.ws = ws
        self.voice = GeminiLiveManager()
        self.history_repository = history_repository

        # ADK agent + runner
        self._agent = create_agent()
        self._runner, self._session_service = create_runner(self._agent)
        self._adk_session_id: str | None = None
        self._user_id = f"user-{session.id}"

    async def initialize(self) -> None:
        """Set up voice connection and ADK session."""
        # Bind sandbox to tool context
        set_sandbox(self.session.sandbox)

        # Connect to Gemini Live
        await self.voice.connect(system_instruction=SYSTEM_PROMPT)

        # Create ADK session
        adk_session = await self._session_service.create_session(
            app_name="nexus", user_id=self._user_id
        )
        self._adk_session_id = adk_session.id

        # Notify frontend
        await self._send_json({
            "type": "sandbox_status",
            "status": "ready",
        })
        await self._send_json({
            "type": "vnc_url",
            "url": self.session.stream_url,
        })

    async def handle_user_audio(self, pcm_data: bytes) -> None:
        """Forward mic audio to Gemini Live."""
        await self.voice.send_audio(pcm_data)
        self.session.touch()

    async def handle_text_input(self, text: str) -> None:
        """Handle direct text input (bypass voice)."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="typed", text=text)
        await self._run_agent(text)

    async def handle_user_utterance(self, text: str) -> None:
        """Called when Gemini Live produces a final user transcript."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="voice", text=text)
        await self._run_agent(text)

    async def handle_analyze_screen(self) -> None:
        """Take screenshot and send analysis to frontend."""
        sandbox = self.session.sandbox
        img_b64 = sandbox.screenshot_base64()
        await self._send_json({
            "type": "agent_screenshot",
            "image_b64": img_b64,
            "analysis": "Screenshot captured. Sending to agent...",
        })
        # Feed screenshot context to agent
        await self._run_agent("Look at the current screen and describe what you see.")

    async def run_voice_receive_loop(self) -> None:
        """Background task: read from Gemini Live, forward to frontend."""
        try:
            async for event_type, data in self.voice.receive_events():
                if event_type == "audio":
                    await self.ws.send_bytes(data)
                elif event_type == "user_transcript":
                    # User speech transcribed — trigger agent
                    await self.handle_user_utterance(data)
                elif event_type == "agent_transcript":
                    await self._send_json({
                        "type": "transcript",
                        "role": "agent",
                        "text": data,
                    })
        except Exception:
            logger.exception("Voice receive loop error")

    async def close(self) -> None:
        """Shut down orchestrator resources."""
        await self.voice.close()

    # ── Private ────────────────────────────────────────────────

    async def _run_agent(self, message: str) -> None:
        """Run an ADK agent turn and stream events to frontend."""
        self.session.touch()

        try:
            response = await run_agent_turn(
                runner=self._runner,
                session_service=self._session_service,
                session_id=self._adk_session_id,
                user_id=self._user_id,
                message=message,
                event_callback=self._on_agent_event,
            )

            if response:
                # Send agent text response
                await self._send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": response,
                })
                await self._persist_message(role="agent", source="agent", text=response)
                # Feed to Gemini Live for TTS
                try:
                    await self.voice.send_text(response)
                except Exception:
                    logger.warning("Failed to send TTS for response")

                await self._send_json({
                    "type": "agent_complete",
                    "summary": response[:200],
                })
                await self._mark_summary(response)

        except Exception:
            logger.exception("Agent turn failed")
            await self._mark_summary("Agent encountered an error processing your request.", status="error", error_code="AGENT_ERROR")
            await self._send_json({
                "type": "error",
                "code": "AGENT_ERROR",
                "message": "Agent encountered an error processing your request.",
            })

    async def _on_agent_event(self, event: Any) -> None:
        """Callback for each ADK agent event — stream to frontend."""
        try:
            # Tool calls
            if event.actions and event.actions.tool_calls:
                for tc in event.actions.tool_calls:
                    await self._send_json({
                        "type": "agent_tool_call",
                        "tool": tc.tool_name if hasattr(tc, 'tool_name') else str(tc),
                        "args": tc.tool_input if hasattr(tc, 'tool_input') else {},
                    })

            # Agent thinking / intermediate content
            if event.content and event.content.parts and not event.is_final_response():
                for part in event.content.parts:
                    if part.text:
                        await self._send_json({
                            "type": "agent_thinking",
                            "content": part.text,
                        })

            # Tool results
            if hasattr(event, 'tool_result') and event.tool_result:
                result = event.tool_result
                tool_name = result.get("tool_name", "unknown") if isinstance(result, dict) else "unknown"
                output = result.get("output", str(result)) if isinstance(result, dict) else str(result)

                await self._send_json({
                    "type": "agent_tool_result",
                    "tool": tool_name,
                    "output": output[:2000],  # Truncate large outputs
                })

                # If the tool returned a screenshot, forward it
                if isinstance(result, dict) and "image" in result:
                    await self._send_json({
                        "type": "agent_screenshot",
                        "image_b64": result["image"],
                        "analysis": "",
                    })

        except Exception:
            logger.exception("Error streaming agent event")

    async def _send_json(self, data: dict) -> None:
        """Send JSON message to the frontend WebSocket."""
        try:
            await self.ws.send_json(data)
        except Exception:
            logger.warning("Failed to send WS message: %s", data.get("type"))

    async def _persist_message(self, *, role: str, source: str, text: str) -> None:
        if not self.history_repository or not text.strip():
            return
        try:
            await self.history_repository.append_message(
                session_id=self.session.id,
                owner_id=self.session.owner_id,
                role=role,
                source=source,
                text=text.strip(),
            )
        except Exception:
            logger.exception("Failed to persist %s message for session %s", role, self.session.id)

    async def _mark_summary(
        self,
        summary: str,
        *,
        status: str | None = None,
        error_code: str | None = None,
    ) -> None:
        if not self.history_repository:
            return
        try:
            await self.history_repository.mark_session_summary(
                self.session.id,
                summary=summary,
                status=status,
                error_code=error_code,
            )
        except Exception:
            logger.exception("Failed to update Firestore summary for session %s", self.session.id)
