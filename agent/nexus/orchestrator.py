"""Orchestrator — wires voice → agent → sandbox → vision → response."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from starlette.websockets import WebSocket

from nexus.agent import create_agent, create_multi_agent, create_runner, run_agent_turn
from nexus.background_tasks import BackgroundTaskManager
from nexus.history_repository import FirestoreHistoryRepository
from nexus.tools._context import set_sandbox, set_bg_task_manager
from nexus.config import settings
from nexus.prompts.system import SYSTEM_PROMPT
from nexus.usage import TokenUsageRecord

if TYPE_CHECKING:
    from nexus.session import Session

logger = logging.getLogger(__name__)


class _AgentStopped(Exception):
    """Raised inside the event callback to break out of the ADK agent loop."""


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
        self.voice = None
        self._voice_connected = False
        self._voice_connect_task: asyncio.Task | None = None
        self._voice_reconnect_task: asyncio.Task | None = None
        self._voice_connection_error_cls: type[Exception] | None = None
        self.history_repository = history_repository

        # Create voice manager when Google project is configured (uses Vertex AI ADC)
        if settings.google_project_id:
            from nexus.voice import GeminiLiveManager, VoiceConnectionError
            self.voice = GeminiLiveManager()
            self._voice_connection_error_cls = VoiceConnectionError

        # ADK agent + runner (multi-agent or single-agent based on config)
        if settings.use_multi_agent:
            self._agent = create_multi_agent()
            logger.info("Using multi-agent orchestrator mode")
        else:
            self._agent = create_agent()
            logger.info("Using single-agent mode")
        self._runner, self._session_service = create_runner(self._agent)
        self._adk_session_id: str | None = None
        self._user_id = f"user-{session.id}"
        self._active_agent: str = "nexus_orchestrator"

        # Background task manager
        self.bg_task_manager = BackgroundTaskManager(send_json=self._send_json)

        # Tracks the currently running agent turn so it can be cancelled
        self._agent_task: asyncio.Task | None = None
        self._stop_requested: bool = False

    async def initialize(self) -> None:
        """Set up voice connection and ADK session."""
        # Bind sandbox and bg task manager to tool context
        set_sandbox(self.session.sandbox)
        set_bg_task_manager(self.bg_task_manager)

        # Connect to Gemini Live in the background so text sessions become ready immediately.
        if self.voice:
            self._voice_connect_task = asyncio.create_task(self._connect_voice())
        else:
            logger.info("No Google API key — voice disabled, text input works")
            self._voice_connected = False

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
        if self.session.stream_url:
            await self._send_json({
                "type": "vnc_url",
                "url": self.session.stream_url,
            })

    async def handle_user_audio(self, pcm_data: bytes) -> None:
        """Forward mic audio to Gemini Live."""
        self.session.touch()
        if not self._is_voice_ready():
            return
        try:
            await self.voice.send_audio(pcm_data)
        except Exception as exc:
            if self._is_voice_connection_error(exc):
                self._voice_connected = False
                logger.warning(
                    "Gemini Live disconnected while sending user audio for session %s",
                    self.session.id,
                )
                self._schedule_voice_reconnect("sending user audio")
                return
            raise

    async def handle_text_input(self, text: str) -> None:
        """Handle direct text input (bypass voice)."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="typed", text=text)
        await self._run_agent_tracked(text)

    def handle_permission_response(self, task_id: str, approved: bool) -> None:
        """Route a permission_response from the frontend to the bg task manager."""
        self.bg_task_manager.handle_permission_response(task_id, approved)

    async def handle_user_utterance(self, text: str) -> None:
        """Called when Gemini Live produces a final user transcript."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="voice", text=text)
        await self._run_agent_tracked(text)

    async def handle_analyze_screen(self) -> None:
        """Take screenshot and send analysis to frontend."""
        sandbox = self.session.sandbox
        try:
            loop = asyncio.get_running_loop()
            img_b64 = await loop.run_in_executor(None, sandbox.screenshot_base64)
        except Exception as exc:
            logger.exception("Screenshot capture failed: %s", exc)
            await self._send_json({
                "type": "agent_screenshot",
                "error": "Screenshot capture failed",
            })
            return
        await self._send_json({
            "type": "agent_screenshot",
            "image_b64": img_b64,
            "analysis": "Screenshot captured. Sending to agent...",
        })
        # Feed screenshot context to agent
        await self._run_agent_tracked("Look at the current screen and describe what you see.")

    async def stop_agent(self) -> None:
        """Cancel the currently running agent turn."""
        self._stop_requested = True
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
        # Immediately notify frontend so the UI updates without waiting
        await self._send_json({
            "type": "agent_complete",
            "summary": "Stopped by user.",
        })

    async def run_voice_receive_loop(self) -> None:
        """Background task: read from Gemini Live, forward to frontend.

        Includes exponential-backoff reconnection — up to 3 retries on transient
        errors (e.g. Gemini Live 1011 service unavailable).
        """
        if self._voice_connect_task:
            await self._voice_connect_task

        if not self.voice:
            return

        if not self._is_voice_ready():
            if not await self._start_or_join_voice_reconnect("starting voice session"):
                return

        while True:
            should_reconnect = False
            try:
                async for event_type, data in self.voice.receive_events():
                    if event_type == "audio":
                        await self.ws.send_bytes(data)
                    elif event_type == "user_transcript":
                        await self.handle_user_utterance(data)
                    elif event_type == "agent_transcript":
                        await self._send_json({
                            "type": "transcript",
                            "role": "agent",
                            "text": data,
                        })
                    elif event_type == "usage":
                        await self._persist_token_usage(data)
                if self._is_voice_ready():
                    break
                should_reconnect = True
                logger.warning(
                    "Gemini Live receive loop ended after disconnect for session %s",
                    self.session.id,
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                if self._is_voice_connection_error(exc):
                    self._voice_connected = False
                    should_reconnect = True
                    logger.warning(
                        "Gemini Live receive loop lost connection for session %s: %s",
                        self.session.id,
                        exc,
                    )
                else:
                    logger.exception("Voice receive loop failed for session %s", self.session.id)
                    break

            if should_reconnect and not await self._start_or_join_voice_reconnect("streaming voice events"):
                break

    async def close(self) -> None:
        """Shut down orchestrator resources."""
        if self._voice_connect_task and not self._voice_connect_task.done():
            self._voice_connect_task.cancel()
            try:
                await self._voice_connect_task
            except asyncio.CancelledError:
                pass
        if self._voice_reconnect_task and not self._voice_reconnect_task.done():
            self._voice_reconnect_task.cancel()
            try:
                await self._voice_reconnect_task
            except asyncio.CancelledError:
                pass
        if self.voice:
            await self.voice.close()

    # ── Private ────────────────────────────────────────────────

    async def _run_agent_tracked(self, message: str) -> None:
        """Wrap _run_agent in a cancellable task and await it."""
        self._stop_requested = False
        self._agent_task = asyncio.create_task(self._run_agent(message))
        try:
            await self._agent_task
        except asyncio.CancelledError:
            logger.info("Agent turn cancelled by user for session %s", self.session.id)
            self._active_agent = "nexus_orchestrator"
            # agent_complete already sent by stop_agent(), skip here

    async def _run_agent(self, message: str) -> None:
        """Run an ADK agent turn and stream events to frontend."""
        self.session.touch()

        # Extend sandbox timeout before each agent turn to prevent mid-task death
        try:
            self.session.sandbox.extend_timeout(300)
        except Exception:
            logger.debug("Could not extend sandbox timeout", exc_info=True)

        try:
            result = await run_agent_turn(
                runner=self._runner,
                session_service=self._session_service,
                session_id=self._adk_session_id,
                user_id=self._user_id,
                message=message,
                event_callback=self._on_agent_event,
            )
            for usage in result.usage_records:
                await self._persist_token_usage(usage)

            if result.response:
                # Send agent text response
                await self._send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": result.response,
                })
                await self._persist_message(role="agent", source="agent", text=result.response)
                # Feed to Gemini Live for TTS
                if self._is_voice_ready():
                    try:
                        await self.voice.send_text(result.response)
                    except Exception as exc:
                        if self._is_voice_connection_error(exc):
                            self._voice_connected = False
                            logger.warning(
                                "Gemini Live disconnected while sending TTS for session %s",
                                self.session.id,
                            )
                            self._schedule_voice_reconnect("sending TTS")
                        else:
                            logger.warning("Failed to send TTS for response", exc_info=True)

                await self._send_json({
                    "type": "agent_complete",
                    "summary": result.response[:200],
                })
                await self._mark_summary(result.response)

        except _AgentStopped:
            logger.info("Agent stopped via _AgentStopped for session %s", self.session.id)

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
        # Bail out early if stop was requested
        if self._stop_requested:
            raise _AgentStopped()

        try:
            # Detect agent delegation (sub-agent transfer)
            author = getattr(event, "author", None)
            if author and author != self._active_agent:
                await self._send_json({
                    "type": "agent_delegation",
                    "from": self._active_agent,
                    "to": author,
                })
                self._active_agent = author

            function_calls = self._extract_function_calls(event)

            for fc in function_calls:
                tool_name = self._get_attr(fc, "name", "tool_name") or str(fc)
                tool_args = self._get_attr(fc, "args", "tool_input") or {}
                await self._send_json({
                    "type": "agent_tool_call",
                    "tool": tool_name,
                    "args": self._coerce_mapping(tool_args),
                })

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) or []
            is_final = self._is_final_response(event)

            for part in parts:
                text = getattr(part, "text", None)
                if text and not is_final:
                    await self._send_json({
                        "type": "agent_thinking",
                        "content": text,
                    })

                fn_resp = getattr(part, "function_response", None)
                if fn_resp:
                    tool_name = self._get_attr(fn_resp, "name") or "unknown"
                    output = self._get_attr(fn_resp, "response")
                    output_mapping = self._coerce_mapping(output)
                    output_str = str(output if output is not None else "")[:2000]

                    await self._send_json({
                        "type": "agent_tool_result",
                        "tool": tool_name,
                        "output": output_str,
                    })

                    if tool_name == "take_screenshot":
                        from nexus.tools.screen import get_last_screenshot_b64

                        img_b64 = get_last_screenshot_b64()
                        if img_b64:
                            await self._send_json({
                                "type": "agent_screenshot",
                                "image_b64": img_b64,
                                "analysis": output_mapping.get("description", ""),
                            })

        except Exception:
            logger.exception("Error streaming agent event")

    async def _connect_voice(self) -> None:
        """Connect to Gemini Live without blocking session readiness."""
        if not self.voice:
            return

        try:
            # Fetch user voice preference
            voice_name = "Kore"
            if self.history_repository:
                try:
                    user_prefs = await self.history_repository.get_user_settings(self.session.owner_id)
                    voice_setting = user_prefs.get("settings", {}).get("voiceId")
                    if voice_setting:
                        # Map UI voice names to Gemini supported voices (Kore, Aoede, Puck, Charon, Fenrir)
                        vmap = {
                            "Calm_Woman": "Kore",
                            "Authoritative_Male": "Charon",
                            "Neutral_Assist": "Aoede",
                            "Dynamic_Guide": "Fenrir"
                        }
                        voice_name = vmap.get(voice_setting, "Kore")
                except Exception:
                    logger.debug("Failed to get user voice preference", exc_info=True)

            await self.voice.connect(system_instruction=SYSTEM_PROMPT, voice_name=voice_name)
            self._voice_connected = self.voice.connected
            logger.info("Gemini Live voice connected with voice %s", voice_name)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._voice_connected = False
            logger.warning("Gemini Live connection failed — voice disabled, text input still works")

    def _is_voice_ready(self) -> bool:
        return bool(self.voice and self._voice_connected and self.voice.connected)

    def _is_voice_connection_error(self, exc: BaseException) -> bool:
        return bool(
            self._voice_connection_error_cls
            and isinstance(exc, self._voice_connection_error_cls)
        )

    def _schedule_voice_reconnect(self, reason: str) -> None:
        if not self.voice:
            return
        if self._voice_reconnect_task and not self._voice_reconnect_task.done():
            return
        self._voice_reconnect_task = asyncio.create_task(self._reconnect_voice(reason))

    async def _start_or_join_voice_reconnect(self, reason: str) -> bool:
        if not self.voice:
            return False
        if self._voice_reconnect_task and not self._voice_reconnect_task.done():
            return await self._voice_reconnect_task
        self._voice_reconnect_task = asyncio.create_task(self._reconnect_voice(reason))
        return await self._voice_reconnect_task

    async def _reconnect_voice(self, reason: str) -> bool:
        if not self.voice:
            return False

        max_retries = 3
        self._voice_connected = False

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                await asyncio.sleep(2.0 * (2 ** (attempt - 2)))

            await self._send_json({
                "type": "voice_status",
                "status": "reconnecting",
                "message": f"Voice reconnecting... (attempt {attempt}/{max_retries})",
            })

            try:
                await self.voice.close()
                await self._connect_voice()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Voice reconnect attempt %d/%d raised an exception for session %s",
                    attempt,
                    max_retries,
                    self.session.id,
                    exc_info=True,
                )

            if self._is_voice_ready():
                await self._send_json({
                    "type": "voice_status",
                    "status": "connected",
                    "message": "Voice reconnected.",
                })
                logger.info(
                    "Gemini Live voice reconnected for session %s after %s",
                    self.session.id,
                    reason,
                )
                return True

        await self._send_json({
            "type": "voice_status",
            "status": "disconnected",
            "message": "Voice connection lost. Text input still works.",
        })
        logger.warning(
            "Gemini Live voice could not reconnect for session %s after %s",
            self.session.id,
            reason,
        )
        return False

    def _extract_function_calls(self, event: Any) -> list[Any]:
        """Return tool calls from the different ADK event shapes."""
        if hasattr(event, "get_function_calls"):
            try:
                calls = event.get_function_calls() or []
                if calls:
                    return list(calls)
            except Exception:
                logger.debug("get_function_calls() failed", exc_info=True)

        actions = getattr(event, "actions", None)
        tool_calls = getattr(actions, "tool_calls", None) if actions else None
        if tool_calls:
            return list(tool_calls)

        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        calls: list[Any] = []
        for part in parts:
            function_call = getattr(part, "function_call", None)
            if function_call:
                calls.append(function_call)
        return calls

    def _is_final_response(self, event: Any) -> bool:
        """Safely detect final ADK responses across API variants."""
        is_final_response = getattr(event, "is_final_response", None)
        if callable(is_final_response):
            try:
                return bool(is_final_response())
            except Exception:
                logger.debug("is_final_response() failed", exc_info=True)
        return False

    def _get_attr(self, obj: Any, *names: str) -> Any:
        """Return the first present attribute or mapping key."""
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            if hasattr(obj, name):
                return getattr(obj, name)
        return None

    def _coerce_mapping(self, value: Any) -> dict[str, Any]:
        """Convert ADK/protobuf-ish payloads into JSON-safe dicts when possible."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "items"):
            try:
                return dict(value.items())
            except Exception:
                pass
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                pass
        if hasattr(value, "__dict__"):
            return {
                key: raw
                for key, raw in vars(value).items()
                if not key.startswith("_")
            }
        return {"value": str(value)}

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

    async def _persist_token_usage(self, usage: TokenUsageRecord) -> None:
        if not self.history_repository:
            return
        try:
            await self.history_repository.append_token_usage(
                session_id=self.session.id,
                owner_id=self.session.owner_id,
                source=usage.source,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
        except Exception:
            logger.exception(
                "Failed to persist token usage for session %s from %s",
                self.session.id,
                usage.source,
            )

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
