"""Orchestrator — wires voice → agent → sandbox → vision → response."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import logging
from typing import TYPE_CHECKING, Any

from starlette.websockets import WebSocket, WebSocketState

from nexus.agent import AgentTurnResult, create_agent, create_multi_agent, create_runner, run_agent_turn
from nexus.background_tasks import BackgroundTask, BackgroundTaskManager
from nexus.billing import calculate_screenshot_credits
from nexus.history_repository import FirestoreHistoryRepository
from nexus.runtime_config import SessionRuntimeConfig
from nexus.sandbox import SandboxDeadError
from nexus.tools._context import (
    set_bg_task_manager,
    set_run_id,
    set_runtime_config,
    set_sandbox,
    set_session_id,
    set_workspace_path,
)
from nexus.config import settings
from nexus.prompts.system import SYSTEM_PROMPT, VOICE_SYSTEM_PROMPT
from nexus.tools.workspace import (
    derive_session_workspace_path,
    derive_workspace_path,
    prepare_task_workspace,
    write_workspace_file,
)
from nexus.usage import TokenUsageRecord

if TYPE_CHECKING:
    from nexus.session import Session

logger = logging.getLogger(__name__)


class _AgentStopped(Exception):
    """Raised inside the event callback to break out of the ADK agent loop."""


class QuotaExceededError(Exception):
    """Raised when the user's starter-plan credits have been exhausted."""


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
        self.runtime_config: SessionRuntimeConfig = session.runtime_config
        self._ws_send_lock: asyncio.Lock = getattr(ws, "_cocomputer_send_lock", asyncio.Lock())
        self.voice = None
        self._voice_connected = False
        self._voice_connect_task: asyncio.Task | None = None
        self._voice_reconnect_task: asyncio.Task | None = None
        self._voice_connection_error_cls: type[Exception] | None = None
        self.history_repository = history_repository

        # Only create voice manager when Gemini credentials are available
        if self.runtime_config.gemini_available:
            from nexus.voice import GeminiLiveManager, VoiceConnectionError
            self.voice = GeminiLiveManager(self.runtime_config)
            self._voice_connection_error_cls = VoiceConnectionError

        # ADK agent + runner (multi-agent or single-agent based on config)
        if settings.use_multi_agent:
            self._agent = create_multi_agent(self.runtime_config)
            logger.info("Using multi-agent orchestrator mode")
        else:
            self._agent = create_agent(self.runtime_config)
            logger.info("Using single-agent mode")
        self._runner, self._session_service = create_runner(self._agent)
        self._adk_session_id: str | None = None
        self._user_id = f"user-{session.id}"
        self._active_agent: str = "nexus_orchestrator"

        # Background task manager
        self.bg_task_manager = BackgroundTaskManager(send_json=self._send_json)
        self.bg_task_manager.set_callbacks(
            on_permission_requested=self._on_permission_requested,
            on_permission_resolved=self._on_permission_resolved,
            on_task_started=self._on_background_task_started,
            on_task_finished=self._on_background_task_finished,
        )
        self._current_run_id = session.current_run_id
        self._current_turn_step_id: str | None = None
        self._tool_step_ids: dict[str, list[str]] = {}

        # Tracks the currently running agent turn so it can be cancelled
        self._agent_task: asyncio.Task | None = None
        self._stop_requested: bool = False
        self._ws_connected: bool = True

        # Voice is lazy — only connects when user explicitly starts mic
        self._voice_started = asyncio.Event()

        # Compact memory injected into the first agent turn on reconnect/resume.
        self._prior_context_packet: dict[str, Any] | None = None
        self._prior_context_fallback: str | None = None
        self._seed_context: str = session.seed_context.strip()
        self._last_user_message: str = ""
        self._turn_screenshot_count: int = 0
        self._turn_tool_summaries: list[str] = []
        self._budget_stop_requested: bool = False
        self._budget_stop_reason: str = ""
        self._workspace_path: str | None = None

    async def initialize(self) -> None:
        """Set up ADK session. Voice connection is deferred until user starts mic."""
        # Bind sandbox and bg task manager to tool context
        set_sandbox(self.session.sandbox)
        set_bg_task_manager(self.bg_task_manager)
        set_runtime_config(self.runtime_config)
        set_session_id(self.session.id)
        self._bind_workspace_context()
        workspace_root_ready = await self._ensure_session_workspace_root()
        if not workspace_root_ready:
            logger.warning(
                "Continuing session %s initialization without a prepared workspace root",
                self.session.id,
            )

        # Voice is NOT connected here — deferred until start_voice() is called
        if self.voice:
            logger.info("Voice available — waiting for user to start mic")
        else:
            logger.info("No Google credentials — voice disabled, text input works")

        # Create ADK session
        adk_session = await self._session_service.create_session(
            app_name="nexus", user_id=self._user_id
        )
        self._adk_session_id = adk_session.id

        # Load compact session memory so resume/continue turns stay cheap.
        if self.history_repository:
            try:
                stored_session = await self.history_repository.get_session(self.session.id)
                if stored_session and stored_session.context_packet:
                    self._prior_context_packet = stored_session.context_packet
                    logger.info("Using cached context packet for session %s", self.session.id)
                else:
                    await self.history_repository.refresh_session_handoff(
                        self.session.id,
                        owner_id=self.session.owner_id,
                    )
                    refreshed_session = await self.history_repository.get_session(self.session.id)
                    if refreshed_session and refreshed_session.context_packet:
                        self._prior_context_packet = refreshed_session.context_packet
                        logger.info(
                            "Rebuilt context packet for session %s during initialize",
                            self.session.id,
                        )
                    else:
                        messages = await self.history_repository.get_session_messages(self.session.id)
                        if messages:
                            self._prior_context_packet = self._build_local_context_packet(messages)
                            logger.info(
                                "Using local compact fallback packet with %d messages for session %s",
                                len(messages),
                                self.session.id,
                            )
            except Exception:
                logger.warning("Failed to load history for replay", exc_info=True)

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
        # Tell frontend voice is available but not yet connected
        await self._send_json({
            "type": "voice_status",
            "status": "available" if self.voice else "unavailable",
            "message": "Voice ready — click mic to connect." if self.voice else "Voice unavailable (no credentials).",
        })
        if self._current_run_id:
            await self._send_json({
                "type": "run_status",
                "run": self._run_payload(status=self.session.run_status),
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

    async def start_voice(self) -> None:
        """Connect to Gemini Live on demand (triggered by user clicking mic)."""
        if not self.voice:
            await self._send_json({
                "type": "voice_status",
                "status": "unavailable",
                "message": "Voice is not available (no credentials configured).",
            })
            return

        if self._is_voice_ready():
            await self._send_json({
                "type": "voice_status",
                "status": "connected",
                "message": "Voice already connected.",
            })
            return

        await self._send_json({
            "type": "voice_status",
            "status": "connecting",
            "message": "Connecting voice...",
        })

        self._voice_connect_task = asyncio.create_task(self._connect_voice())
        await self._voice_connect_task

        if self._is_voice_ready():
            self._voice_started.set()
            await self._send_json({
                "type": "voice_status",
                "status": "connected",
                "message": "Voice connected.",
            })
        else:
            await self._send_json({
                "type": "voice_status",
                "status": "disconnected",
                "message": "Voice connection failed. Text input still works.",
            })

    async def handle_text_input(self, text: str) -> None:
        """Handle direct text input (bypass voice)."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="typed", text=text)
        await self._run_agent_tracked(await self._build_turn_input(text), source="typed")

    def handle_permission_response(self, task_id: str, approved: bool) -> None:
        """Route a permission_response from the frontend to the bg task manager."""
        self.bg_task_manager.handle_permission_response(task_id, approved)

    async def handle_user_utterance(self, text: str) -> None:
        """Called when Gemini Live produces a final user transcript."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="voice", text=text)
        await self._run_agent_tracked(await self._build_turn_input(text), source="voice")

    async def handle_analyze_screen(self) -> None:
        """Take screenshot and send analysis to frontend."""
        sandbox = self.session.sandbox
        screen_step_id = await self._create_step(
            step_type="system_event",
            title="Analyze current screen",
            detail="Manual screen analysis requested.",
            source="system",
        )

        # Auto-reconnect sandbox if it died
        if not sandbox.is_alive:
            reconnected = await self._reconnect_sandbox()
            if not reconnected:
                await self._fail_step(
                    screen_step_id,
                    detail="Sandbox is not running and could not be reconnected.",
                    error="Sandbox is not running and could not be reconnected.",
                )
                await self._send_json({
                    "type": "agent_screenshot",
                    "error": "Sandbox is not running and could not be reconnected.",
                })
                return
            sandbox = self.session.sandbox

        try:
            loop = asyncio.get_running_loop()
            img_b64 = await loop.run_in_executor(None, sandbox.screenshot_base64)
        except SandboxDeadError:
            logger.warning("Sandbox died during screenshot for session %s — reconnecting", self.session.id)
            reconnected = await self._reconnect_sandbox()
            if reconnected:
                try:
                    img_b64 = await loop.run_in_executor(None, self.session.sandbox.screenshot_base64)
                except Exception:
                    await self._fail_step(
                        screen_step_id,
                        detail="Screenshot failed after reconnect.",
                        error="Screenshot failed after reconnect.",
                    )
                    await self._send_json({"type": "agent_screenshot", "error": "Screenshot failed after reconnect"})
                    return
            else:
                await self._fail_step(
                    screen_step_id,
                    detail="Sandbox died and could not reconnect.",
                    error="Sandbox died and could not reconnect.",
                )
                await self._send_json({"type": "agent_screenshot", "error": "Sandbox died and could not reconnect"})
                return
        except Exception as exc:
            logger.exception("Screenshot capture failed: %s", exc)
            await self._fail_step(
                screen_step_id,
                detail="Screenshot capture failed.",
                error=str(exc),
            )
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
        await self._complete_step(
            screen_step_id,
            detail="Screenshot captured and queued for analysis.",
        )
        await self._create_artifact(
            kind="screenshot_reference",
            title="Manual screen capture",
            preview="Screenshot captured and queued for analysis.",
            source_step_id=screen_step_id,
            metadata={"source": "manual_screen_analysis"},
        )
        # Feed screenshot context to agent
        await self._run_agent_tracked(
            "Look at the current screen and describe what you see.",
            source="screen",
        )

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

        Waits for start_voice() to be called, then loops with exponential-backoff
        reconnection — up to 3 retries on transient errors.
        """
        if not self.voice:
            return

        # Wait until user explicitly starts voice
        await self._voice_started.wait()

        if self._voice_connect_task:
            await self._voice_connect_task

        if not self._is_voice_ready():
            if not await self._start_or_join_voice_reconnect("starting voice session"):
                return

        while self._ws_connected:
            should_reconnect = False
            try:
                async for event_type, data in self.voice.receive_events():
                    if not self._ws_connected:
                        break
                    if event_type == "audio":
                        await self._send_bytes(data)
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

    _RATE_LIMIT_MAX_RETRIES = 4
    _RATE_LIMIT_BASE_WAIT = 10.0  # seconds; doubles each attempt: 10, 20, 40, 80
    _RATE_LIMIT_PATTERNS = ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "too many requests")
    _RESUME_PACKET_SOFT_TOKENS = 2_000
    _RESUME_PACKET_HARD_TOKENS = 3_200
    _SCREENSHOT_WARN_THRESHOLD = 6
    _SCREENSHOT_WARNING_INTERVAL = 4

    def _is_rate_limit_error(self, exc: BaseException) -> bool:
        msg = str(exc).lower()
        return any(p.lower() in msg for p in self._RATE_LIMIT_PATTERNS)

    def _task_model_candidates(self) -> tuple[str, ...]:
        primary = self.runtime_config.gemini_agent_model
        ordered: list[str] = []
        seen: set[str] = set()
        for model in (primary, *self.runtime_config.gemini_agent_fallback_models):
            if not model or model in seen:
                continue
            seen.add(model)
            ordered.append(model)
        return tuple(ordered) or (primary,)

    def _rate_limit_source_label(self) -> str:
        return "Vertex AI" if self.runtime_config.use_vertex_ai else "Gemini API"

    def _rebuild_agent_for_task_model(self, task_model: str) -> None:
        if task_model == self.runtime_config.gemini_agent_model:
            return

        self.runtime_config = replace(self.runtime_config, gemini_agent_model=task_model)
        self.session.runtime_config = self.runtime_config
        set_runtime_config(self.runtime_config)

        if settings.use_multi_agent:
            self._agent = create_multi_agent(self.runtime_config, task_model_override=task_model)
        else:
            self._agent = create_agent(self.runtime_config, task_model_override=task_model)
        self._runner, self._session_service = create_runner(
            self._agent,
            session_service=self._session_service,
        )
        logger.info(
            "Switched task model for session %s to %s",
            self.session.id,
            task_model,
        )

    async def _run_agent_with_retry(self, message: str):
        """Run agent turn with automatic retry on rate-limit (429) errors.

        Uses exponential backoff (10s, 20s, 40s, 80s) to avoid hammering the
        active provider while it recovers. Sessions can also fall back to
        alternate task models after retries are exhausted.
        """
        last_exc: Exception | None = None
        model_candidates = self._task_model_candidates()

        for model_index, task_model in enumerate(model_candidates, start=1):
            if task_model != self.runtime_config.gemini_agent_model:
                self._rebuild_agent_for_task_model(task_model)

            for attempt in range(1, self._RATE_LIMIT_MAX_RETRIES + 1):
                try:
                    return await run_agent_turn(
                        runner=self._runner,
                        session_service=self._session_service,
                        session_id=self._adk_session_id,
                        user_id=self._user_id,
                        message=message,
                        runtime_config=self.runtime_config,
                        event_callback=self._on_agent_event,
                    )
                except _AgentStopped:
                    raise
                except Exception as exc:
                    if not self._is_rate_limit_error(exc):
                        logger.error(
                            "Agent turn failed with unexpected error for session %s",
                            self.session.id,
                            exc_info=True,
                        )
                        return AgentTurnResult(
                            response=None,
                            usage_records=[],
                            error=str(exc) or "Agent encountered an unexpected error.",
                        )

                    last_exc = exc
                    is_last_retry = attempt == self._RATE_LIMIT_MAX_RETRIES
                    has_next_model = model_index < len(model_candidates)

                    if is_last_retry:
                        if has_next_model:
                            next_model = model_candidates[model_index]
                            logger.warning(
                                "Task model %s exhausted retries for session %s — switching to %s: %s",
                                task_model,
                                self.session.id,
                                next_model,
                                exc,
                            )
                            await self._send_json({
                                "type": "agent_thinking",
                                "content": (
                                    f"Task model {task_model} hit quota limits. "
                                    f"Switching to fallback model {next_model}."
                                ),
                            })
                            break
                        continue

                    wait = self._RATE_LIMIT_BASE_WAIT * (2 ** (attempt - 1))
                    logger.warning(
                        "Rate limited (attempt %d/%d model=%s) for session %s — waiting %.0fs: %s",
                        attempt,
                        self._RATE_LIMIT_MAX_RETRIES,
                        task_model,
                        self.session.id,
                        wait,
                        exc,
                    )
                    await self._send_json({
                        "type": "agent_thinking",
                        "content": (
                            f"Temporarily rate-limited by {self._rate_limit_source_label()} "
                            f"on {task_model} — backing off {wait:.0f}s "
                            f"(attempt {attempt}/{self._RATE_LIMIT_MAX_RETRIES})..."
                        ),
                    })
                    await asyncio.sleep(wait)

        raise RuntimeError(
            "Rate limit exceeded after retries across task models "
            f"{', '.join(model_candidates)}: {last_exc}"
        )

    async def _build_turn_input(self, text: str) -> str:
        """Build the next turn input with compact resume context injected once."""
        self._last_user_message = text.strip()
        parts: list[str] = []

        if self._seed_context:
            parts.append(self._seed_context)

        if self._prior_context_packet:
            serialized, action = self._format_context_packet_for_budget(
                self._prior_context_packet,
                user_text=self._last_user_message,
            )
            estimated_tokens = self._estimate_tokens(serialized) + self._estimate_tokens(self._last_user_message)
            if action:
                await self._emit_budget_warning(
                    state="soft_limit",
                    action=action,
                    message="Compacted resume memory before sending the turn to the model.",
                    projected_total_tokens=estimated_tokens,
                )
            if serialized:
                parts.append(serialized)
                await self._emit_context_packet(
                    stage="resume_injected",
                    packet=self._prior_context_packet,
                    action=action,
                    estimated_tokens=estimated_tokens,
                )
            self._prior_context_packet = None
            self._prior_context_fallback = None
            self._seed_context = ""
        elif self._prior_context_fallback:
            parts.append(self._prior_context_fallback)
            self._prior_context_fallback = None
            self._seed_context = ""
        elif self._seed_context:
            self._seed_context = ""

        if parts:
            joined = "\n\n".join(part for part in parts if part.strip())
            return f"{joined}\n\nUser: {text}"
        return text

    @staticmethod
    def _format_history_context(messages: list[dict]) -> str:
        """Fallback formatter when no cached context packet exists."""
        recent = messages[-4:]
        lines = []
        for msg in recent:
            role = (msg.get("role") or "user").upper()
            text = str(msg.get("text") or "").strip()
            if text:
                lines.append(f"{role}: {text[:300]}")
        if not lines:
            return ""
        history = "\n".join(lines)
        return (
            "[RECENT CONVERSATION FALLBACK]\n"
            f"{history}\n"
            "[END RECENT CONVERSATION FALLBACK]\n\n"
            "Continue naturally from where you left off."
        )

    def _build_local_context_packet(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        recent_turns: list[str] = []
        for message in messages[-4:]:
            role = "User" if message.get("role") == "user" else "Agent"
            text = self._clip_text(message.get("text"), 180)
            if text:
                recent_turns.append(f"{role}: {text}")

        summary = ""
        for message in reversed(messages):
            text = self._clip_text(message.get("text"), 320)
            if text:
                summary = text
                break

        packet = {
            "version": 2,
            "builtAt": "",
            "summary": summary or "Continue from the recent conversation context.",
            "goal": "Continue the previous workspace task.",
            "openTasks": [],
            "recentTurns": recent_turns,
            "latestRunSummary": "",
            "artifactRefs": [],
            "toolMemory": [],
            "workspaceState": "Recovered from recent session messages.",
        }
        digest_source = "|".join(recent_turns) or packet["summary"]
        packet["digest"] = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
        return packet

    @classmethod
    def _estimate_tokens(cls, text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        return max(1, (len(stripped) + 3) // 4)

    @classmethod
    def _format_context_packet(cls, packet: dict[str, Any]) -> str:
        lines = ["[CACHED SESSION CONTEXT]"]
        for label, key in (
            ("Summary", "summary"),
            ("Goal", "goal"),
            ("Latest run summary", "latestRunSummary"),
            ("Workspace state", "workspaceState"),
        ):
            value = packet.get(key)
            if isinstance(value, str) and value.strip():
                lines.append(f"{label}: {value.strip()}")
        for label, key in (
            ("Open tasks", "openTasks"),
            ("Recent turns", "recentTurns"),
            ("Artifacts", "artifactRefs"),
            ("Tool memory", "toolMemory"),
        ):
            values = packet.get(key)
            if isinstance(values, list):
                compact = [str(item).strip() for item in values if str(item).strip()]
                if compact:
                    lines.append(f"{label}:")
                    lines.extend(f"- {item}" for item in compact[:4])
        lines.append("[END CACHED SESSION CONTEXT]")
        lines.append("Continue naturally from where you left off.")
        return "\n".join(lines)

    @staticmethod
    def _context_packet_for_client(packet: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": int(packet.get("version", 2) or 2),
            "built_at": str(packet.get("builtAt", "") or ""),
            "summary": str(packet.get("summary", "") or ""),
            "goal": str(packet.get("goal", "") or ""),
            "open_tasks": [str(item) for item in (packet.get("openTasks") or []) if str(item).strip()],
            "recent_turns": [str(item) for item in (packet.get("recentTurns") or []) if str(item).strip()],
            "latest_run_summary": str(packet.get("latestRunSummary", "") or ""),
            "artifact_refs": [str(item) for item in (packet.get("artifactRefs") or []) if str(item).strip()],
            "tool_memory": [str(item) for item in (packet.get("toolMemory") or []) if str(item).strip()],
            "workspace_state": str(packet.get("workspaceState", "") or ""),
            "digest": str(packet.get("digest", "") or ""),
        }

    async def _emit_context_packet(
        self,
        *,
        stage: str,
        packet: dict[str, Any],
        action: str | None = None,
        estimated_tokens: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "context_packet",
            "stage": stage,
            "action": action or "full",
            "packet": self._context_packet_for_client(packet),
            "reasoning_model": self.runtime_config.gemini_agent_model,
            "vision_model": self.runtime_config.gemini_vision_model,
        }
        if estimated_tokens is not None:
            payload["estimated_tokens"] = estimated_tokens
        await self._send_json(payload)

    def _format_context_packet_for_budget(
        self,
        packet: dict[str, Any],
        *,
        user_text: str,
    ) -> tuple[str, str | None]:
        def copy_packet() -> dict[str, Any]:
            return {
                **packet,
                "openTasks": list(packet.get("openTasks") or []),
                "recentTurns": list(packet.get("recentTurns") or []),
                "artifactRefs": list(packet.get("artifactRefs") or []),
                "toolMemory": list(packet.get("toolMemory") or []),
            }

        variants: list[tuple[str | None, dict[str, Any]]] = []

        full = copy_packet()
        variants.append((None, full))

        no_artifacts = copy_packet()
        no_artifacts["artifactRefs"] = []
        variants.append(("drop_artifacts", no_artifacts))

        no_recent_turns = copy_packet()
        no_recent_turns["artifactRefs"] = []
        no_recent_turns["recentTurns"] = []
        variants.append(("drop_recent_turns", no_recent_turns))

        reduced_tool_memory = copy_packet()
        reduced_tool_memory["artifactRefs"] = []
        reduced_tool_memory["recentTurns"] = []
        reduced_tool_memory["toolMemory"] = [
            self._clip_text(str(item), 90)
            for item in (packet.get("toolMemory") or [])[:2]
            if self._clip_text(str(item), 90)
        ]
        variants.append(("compress_tool_memory", reduced_tool_memory))

        minimal = copy_packet()
        minimal["artifactRefs"] = []
        minimal["recentTurns"] = []
        minimal["toolMemory"] = []
        minimal["openTasks"] = list(minimal.get("openTasks") or [])[:2]
        variants.append(("summary_only", minimal))

        selected_action: str | None = None
        selected_payload = self._format_context_packet(minimal)
        for action, variant in variants:
            payload = self._format_context_packet(variant)
            projected = self._estimate_tokens(payload) + self._estimate_tokens(user_text)
            if projected <= self._RESUME_PACKET_SOFT_TOKENS:
                return payload, action
            selected_action = action
            selected_payload = payload
        return selected_payload, selected_action

    async def _reconnect_sandbox(self) -> bool:
        """Attempt to create a new sandbox when the current one has died.

        Returns True if reconnect succeeded, False otherwise.
        """
        logger.info("Attempting sandbox reconnect for session %s", self.session.id)
        await self._send_json({"type": "sandbox_status", "status": "reconnecting"})
        await self._send_json({
            "type": "resume_recovery",
            "state": "reconnecting",
            "message": "Reconnecting the sandbox and reusing compact session memory.",
            "reused_context_digest": (
                self._prior_context_packet.get("digest", "")
                if isinstance(self._prior_context_packet, dict)
                else ""
            ),
        })

        try:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, self.session.sandbox.create)
            self.session.sandbox_id = info["sandbox_id"]
            self.session.stream_url = info["stream_url"]
            # Re-bind the new sandbox to the tool context
            set_sandbox(self.session.sandbox)
            self._bind_workspace_context()
            workspace_root_ready = await self._ensure_session_workspace_root()
            if not workspace_root_ready:
                logger.warning(
                    "Sandbox reconnected for session %s without a prepared workspace root",
                    self.session.id,
                )
            await self._send_json({"type": "sandbox_status", "status": "ready"})
            await self._send_json({"type": "vnc_url", "url": self.session.stream_url})
            await self._send_json({
                "type": "resume_recovery",
                "state": "recovered",
                "message": "Sandbox recovered. Continuing with compact session memory.",
                "reused_context_digest": (
                    self._prior_context_packet.get("digest", "")
                    if isinstance(self._prior_context_packet, dict)
                    else ""
                ),
            })
            logger.info(
                "Sandbox reconnected for session %s (new stream_url=%s)",
                self.session.id,
                self.session.stream_url,
            )
            return True
        except Exception as exc:
            logger.exception("Sandbox reconnect failed for session %s: %s", self.session.id, exc)
            await self._send_json({
                "type": "sandbox_status",
                "status": "error",
                "message": f"Failed to reconnect sandbox: {exc}",
            })
            await self._send_json({
                "type": "resume_recovery",
                "state": "failed",
                "message": f"Failed to recover the sandbox: {exc}",
                "reused_context_digest": "",
            })
            return False

    async def _run_agent_tracked(self, message: str, *, source: str) -> None:
        """Wrap _run_agent in a cancellable task and await it."""
        if not self._ws_connected:
            logger.info("Skipping agent turn start for session %s because the WebSocket is disconnected", self.session.id)
            return
        self._stop_requested = False
        self._turn_screenshot_count = 0
        self._turn_tool_summaries = []
        self._budget_stop_requested = False
        self._budget_stop_reason = ""
        await self._prepare_workspace_for_turn(message)
        self._current_turn_step_id = await self._create_step(
            step_type="agent_turn",
            title="Process request",
            detail=self._clip_text(message, 320),
            source=source,
            metadata={"input": self._clip_text(message, 1200), "source": source},
        )
        await self._set_run_status("running")
        self._agent_task = asyncio.create_task(self._run_agent(message))
        try:
            result = await self._agent_task
            if result["status"] == "completed":
                await self._complete_step(
                    self._current_turn_step_id,
                    detail=self._clip_text(result.get("summary") or "Turn completed.", 1500),
                )
                await self._set_run_status("completed")
            elif result["status"] == "cancelled":
                await self._fail_unfinished_tool_steps(status="cancelled", error=result.get("summary"))
                await self._fail_step(
                    self._current_turn_step_id,
                    detail=self._clip_text(result.get("summary") or "Turn cancelled.", 1500),
                    error=result.get("summary"),
                    status="cancelled",
                )
                await self._set_run_status("cancelled")
            else:
                await self._fail_unfinished_tool_steps(status="failed", error=result.get("summary"))
                await self._fail_step(
                    self._current_turn_step_id,
                    detail=self._clip_text(result.get("summary") or "Turn failed.", 1500),
                    error=result.get("summary"),
                )
                await self._set_run_status("failed")
        except asyncio.CancelledError:
            cancel_reason = "WebSocket disconnected." if not self._ws_connected else "Stopped by user."
            if self._ws_connected:
                logger.info("Agent turn cancelled by user for session %s", self.session.id)
            else:
                logger.info("Agent turn cancelled after WebSocket disconnect for session %s", self.session.id)
            self._active_agent = "nexus_orchestrator"
            await self._fail_unfinished_tool_steps(status="cancelled", error=cancel_reason)
            await self._fail_step(
                self._current_turn_step_id,
                detail=cancel_reason,
                error=cancel_reason,
                status="cancelled",
            )
            await self._set_run_status("cancelled")
        finally:
            self._tool_step_ids = {}
            self._active_agent = "nexus_orchestrator"
            self._current_turn_step_id = None

    async def _run_agent(self, message: str) -> dict[str, str]:
        """Run an ADK agent turn and stream events to frontend."""
        self.session.touch()

        if not self._ws_connected:
            logger.info("WebSocket disconnected before agent turn started for session %s", self.session.id)
            return {
                "status": "cancelled",
                "summary": "WebSocket disconnected before the turn started.",
            }

        # Check starter-plan credits before running agent
        if self.history_repository:
            try:
                quota = await self.history_repository.get_user_quota(self.session.owner_id)
                if quota["remaining"] <= 0:
                    await self._send_json({
                        "type": "error",
                        "code": "QUOTA_EXCEEDED",
                        "message": (
                            f"{quota.get('plan_name', settings.default_plan_name)} balance exhausted. "
                            "This development entitlement has no remaining credits."
                        ),
                    })
                    await self._send_json(self._quota_update_payload(quota))
                    return {
                        "status": "failed",
                        "summary": "Starter plan balance exhausted.",
                    }
            except Exception:
                logger.debug("Quota check failed, allowing turn", exc_info=True)

        # Extend sandbox timeout before each agent turn to prevent mid-task death
        try:
            self.session.sandbox.extend_timeout(900)
        except Exception:
            logger.debug("Could not extend sandbox timeout", exc_info=True)

        # Auto-reconnect sandbox if it died before this turn
        if not self.session.sandbox.is_alive:
            reconnected = await self._reconnect_sandbox()
            if not reconnected:
                await self._send_json({
                    "type": "error",
                    "code": "SANDBOX_DEAD",
                    "message": "Sandbox is not running and could not be reconnected. Please start a new session.",
                })
                return {
                    "status": "failed",
                    "summary": "Sandbox is not running and could not be reconnected.",
                }

        try:
            result = await self._run_agent_with_retry(message)
            for usage in result.usage_records:
                await self._persist_token_usage(usage)

            if result.error:
                logger.error(
                    "Agent turn returned an error result for session %s: %s",
                    self.session.id,
                    result.error,
                )
                await self._mark_summary(
                    "Agent encountered an error processing your request.",
                    status="error",
                    error_code="AGENT_ERROR",
                )
                await self._send_json({
                    "type": "error",
                    "code": "AGENT_ERROR",
                    "message": "Agent encountered an error processing your request.",
                    "detail": result.error,
                })
                return {
                    "status": "failed",
                    "summary": result.error,
                }

            # Check if sandbox died during the agent turn
            if not self.session.sandbox.is_alive:
                logger.warning("Sandbox died during agent turn for session %s — reconnecting", self.session.id)
                await self._reconnect_sandbox()

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
                await self._save_final_response(result.response)
                await self._mark_summary(result.response)
                await self._create_artifact(
                    kind="summary",
                    title="Agent summary",
                    preview=self._clip_text(result.response, 280),
                    source_step_id=self._current_turn_step_id,
                    metadata={"source": "agent_complete"},
                )
                return {
                    "status": "completed",
                    "summary": result.response,
                }
            return {
                "status": "completed",
                "summary": "Turn completed.",
            }

        except _AgentStopped:
            if self._budget_stop_requested:
                summary = self._build_budget_partial_summary()
                await self._send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": summary,
                })
                await self._persist_message(role="agent", source="agent", text=summary)
                await self._send_json({
                    "type": "agent_complete",
                    "summary": summary[:200],
                })
                await self._save_final_response(summary)
                await self._mark_summary(summary)
                await self._create_artifact(
                    kind="summary",
                    title="Budget-safe partial summary",
                    preview=self._clip_text(summary, 280),
                    source_step_id=self._current_turn_step_id,
                    metadata={"source": "budget_stop"},
                )
                return {
                    "status": "completed",
                    "summary": summary,
                }
            logger.info("Agent stopped via _AgentStopped for session %s", self.session.id)
            raise

        except Exception as exc:
            logger.exception("Agent turn failed")
            await self._mark_summary("Agent encountered an error processing your request.", status="error", error_code="AGENT_ERROR")
            await self._send_json({
                "type": "error",
                "code": "AGENT_ERROR",
                "message": "Agent encountered an error processing your request.",
                "detail": str(exc) or "Agent encountered an error processing your request.",
            })
            return {
                "status": "failed",
                "summary": str(exc) or "Agent encountered an error processing your request.",
            }

    async def _on_agent_event(self, event: Any) -> None:
        """Callback for each ADK agent event — stream to frontend."""
        # Bail out early if stop was requested
        self._raise_if_agent_should_stop()

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
                self._raise_if_agent_should_stop()
                tool_name = self._get_attr(fc, "name", "tool_name") or str(fc)
                tool_args = self._get_attr(fc, "args", "tool_input") or {}
                if tool_name == "take_screenshot":
                    next_count = self._turn_screenshot_count + 1
                    if (
                        next_count == self._SCREENSHOT_WARN_THRESHOLD
                        or (
                            next_count > self._SCREENSHOT_WARN_THRESHOLD
                            and (next_count - self._SCREENSHOT_WARN_THRESHOLD) % self._SCREENSHOT_WARNING_INTERVAL == 0
                        )
                    ):
                        await self._emit_budget_warning(
                            state="soft_limit",
                            action="prefer_cached_or_delta_analysis",
                            message=(
                                "Heavy screen observation detected. The run will continue, "
                                "but screenshot analysis now prefers cached or delta reuse when possible."
                            ),
                            projected_total_tokens=next_count,
                        )
                step_id = await self._create_step(
                    step_type="tool_call",
                    title=f"Tool: {tool_name}",
                    detail=self._clip_text(self._coerce_mapping(tool_args), 320),
                    source=self._active_agent,
                    metadata={"tool": tool_name, "args": self._coerce_mapping(tool_args)},
                )
                if step_id:
                    self._tool_step_ids.setdefault(tool_name, []).append(step_id)
                await self._send_json({
                    "type": "agent_tool_call",
                    "tool": tool_name,
                    "args": self._coerce_mapping(tool_args),
                })

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) or []
            is_final = self._is_final_response(event)

            for part in parts:
                self._raise_if_agent_should_stop()
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
                    output_str = str(
                        output_mapping.get("summary")
                        or output_mapping.get("description")
                        or output if output is not None else ""
                    )[:2000]
                    step_id = None
                    pending_steps = self._tool_step_ids.get(tool_name, [])
                    if pending_steps:
                        step_id = pending_steps.pop(0)
                        if not pending_steps:
                            self._tool_step_ids.pop(tool_name, None)

                    await self._send_json({
                        "type": "agent_tool_result",
                        "tool": tool_name,
                        "output": output_str,
                    })
                    await self._complete_step(
                        step_id,
                        detail=self._clip_text(output_str, 1500),
                        metadata={"tool": tool_name},
                    )

                    if tool_name == "take_screenshot":
                        from nexus.tools.screen import get_last_screenshot_b64

                        img_b64 = get_last_screenshot_b64()
                        if img_b64:
                            await self._send_json({
                                "type": "agent_screenshot",
                                "image_b64": img_b64,
                                "analysis": output_mapping.get("description", ""),
                            })
                        await self._charge_screenshot_credits(
                            analysis_mode=(
                                output_mapping.get("analysis_mode")
                                if isinstance(output_mapping.get("analysis_mode"), str)
                                else None
                            ),
                        )

                    await self._record_tool_memory(
                        tool_name=tool_name,
                        output_mapping=output_mapping,
                        output_str=output_str,
                        step_id=step_id,
                    )

                    artifact_ref = self._extract_reference_artifact(tool_name, output_mapping, output_str)
                    if artifact_ref:
                        await self._create_artifact(
                            kind=artifact_ref["kind"],
                            title=artifact_ref["title"],
                            preview=artifact_ref["preview"],
                            source_step_id=step_id,
                            path=artifact_ref.get("path"),
                            url=artifact_ref.get("url"),
                            metadata=artifact_ref.get("metadata"),
                        )

        except _AgentStopped:
            raise
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

            await self.voice.connect(system_instruction=VOICE_SYSTEM_PROMPT, voice_name=voice_name)
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

    def mark_ws_disconnected(self) -> None:
        self._ws_connected = False
        self._stop_requested = True

    def _ws_is_open(self) -> bool:
        return (
            self._ws_connected
            and self.ws.client_state == WebSocketState.CONNECTED
            and self.ws.application_state == WebSocketState.CONNECTED
        )

    def _raise_if_agent_should_stop(self) -> None:
        if self._stop_requested:
            raise _AgentStopped()
        if self._ws_is_open():
            return
        if self._ws_connected:
            logger.info("WebSocket disconnected — stopping agent turn early")
        self.mark_ws_disconnected()
        raise _AgentStopped()

    async def _send_bytes(self, data: bytes) -> None:
        try:
            async with self._ws_send_lock:
                if not self._ws_is_open():
                    logger.debug("Skipping WS audio frame — connection not open")
                    return
                await self.ws.send_bytes(data)
        except RuntimeError as exc:
            if "websocket.close" in str(exc) or "response already completed" in str(exc):
                logger.debug("Skipping WS audio frame — connection closed")
                self.mark_ws_disconnected()
            else:
                logger.warning("Failed to send WS audio frame", exc_info=True)
        except Exception:
            if not self._ws_is_open():
                logger.debug("Skipping WS audio frame — connection closed")
                self.mark_ws_disconnected()
                return
            logger.warning("Failed to send WS audio frame", exc_info=True)

    async def _send_json(self, data: dict) -> None:
        """Send JSON message to the frontend WebSocket."""
        message_type = data.get("type")
        try:
            async with self._ws_send_lock:
                if not self._ws_is_open():
                    logger.debug("Skipping WS message %s — connection not open", message_type)
                    return
                await self.ws.send_json(data)
        except RuntimeError as exc:
            if "websocket.close" in str(exc) or "response already completed" in str(exc):
                logger.debug("Skipping WS message %s — connection closed", message_type)
                self.mark_ws_disconnected()
            else:
                logger.warning(
                    "Failed to send WS message: %s",
                    message_type,
                    exc_info=True,
                )
        except Exception:
            if not self._ws_is_open():
                logger.debug("Skipping WS message %s — connection closed", message_type)
                self.mark_ws_disconnected()
                return
            logger.warning(
                "Failed to send WS message: %s",
                message_type,
                exc_info=True,
            )

    @staticmethod
    def _quota_update_payload(quota: dict[str, Any]) -> dict[str, Any]:
        payload = {"type": "quota_update"}
        payload.update(quota)
        return payload

    async def _emit_budget_warning(
        self,
        *,
        state: str,
        action: str,
        message: str,
        projected_total_tokens: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "budget_warning",
            "state": state,
            "action": action,
            "message": message,
            "soft_limit": self._RESUME_PACKET_SOFT_TOKENS,
            "hard_limit": self._RESUME_PACKET_HARD_TOKENS,
        }
        if projected_total_tokens is not None:
            payload["projected_total_tokens"] = projected_total_tokens
        await self._send_json(payload)

    def _build_budget_partial_summary(self) -> str:
        findings = self._turn_tool_summaries[:4]
        lines = [
            "Stopped early to stay within the run budget before the task could expand further.",
        ]
        if self._last_user_message:
            lines.append(f"Task: {self._clip_text(self._last_user_message, 240)}")
        if findings:
            lines.append("Findings so far:")
            lines.extend(f"- {item}" for item in findings)
        if self._budget_stop_reason:
            lines.append(f"Why it stopped: {self._clip_text(self._budget_stop_reason, 240)}")
        lines.append("Continue if you want deeper research or more browsing.")
        return "\n".join(lines)

    async def _record_tool_memory(
        self,
        *,
        tool_name: str,
        output_mapping: dict[str, Any],
        output_str: str,
        step_id: str | None,
    ) -> None:
        summary = ""
        metadata: dict[str, Any] = {"tool": tool_name}

        if tool_name == "take_screenshot":
            summary = self._clip_text(str(output_mapping.get("description") or output_str), 180)
            if not summary:
                return
            self._turn_screenshot_count += 1
            analysis_mode = output_mapping.get("analysis_mode")
            if isinstance(analysis_mode, str) and analysis_mode.strip():
                metadata["analysis_mode"] = analysis_mode.strip()
            delta = output_mapping.get("delta")
            if isinstance(delta, str) and delta.strip():
                metadata["delta"] = delta.strip()
        elif tool_name == "run_command":
            summary = self._clip_text(
                str(output_mapping.get("summary") or output_mapping.get("stderr_excerpt") or output_str),
                180,
            )
            if not summary:
                return
            command = output_mapping.get("command")
            if isinstance(command, str) and command.strip():
                metadata["command"] = self._clip_text(command, 120)
            exit_code = output_mapping.get("exit_code")
            if isinstance(exit_code, int):
                metadata["exit_code"] = exit_code
        else:
            return

        entry = f"{tool_name}: {summary}"
        self._turn_tool_summaries.append(entry)
        self._turn_tool_summaries = self._turn_tool_summaries[-6:]

        if not self.history_repository:
            return
        try:
            content_hash = hashlib.sha256(entry.encode("utf-8")).hexdigest()[:16]
            await self.history_repository.record_tool_memory(
                session_id=self.session.id,
                kind=tool_name,
                summary=summary,
                content_hash=content_hash,
                source_step_id=step_id,
                metadata=metadata,
            )
        except Exception:
            logger.exception("Failed to persist tool memory for session %s", self.session.id)

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
            credits_charged = await self.history_repository.append_token_usage(
                session_id=self.session.id,
                owner_id=self.session.owner_id,
                source=usage.source,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
            # Tokens remain internal telemetry; credits are the user-facing allowance.
            if usage.total_tokens > 0:
                await self.history_repository.increment_user_token_usage(
                    self.session.owner_id,
                    usage.total_tokens,
                )
            if credits_charged > 0:
                quota = await self.history_repository.increment_user_credit_usage(
                    self.session.owner_id,
                    credits_charged,
                )
                await self._send_json(self._quota_update_payload(quota))
        except Exception:
            logger.exception(
                "Failed to persist token usage for session %s from %s",
                self.session.id,
                usage.source,
            )

    async def _charge_screenshot_credits(self, *, analysis_mode: str | None) -> None:
        if not self.history_repository:
            return
        credits = calculate_screenshot_credits(analysis_mode)
        if credits <= 0:
            return
        try:
            await self.history_repository.record_credit_charge(
                session_id=self.session.id,
                owner_id=self.session.owner_id,
                source="vision.screenshot",
                model=self.runtime_config.gemini_vision_model,
                credits=credits,
                metadata={"analysis_mode": analysis_mode or "vision_full"},
            )
            quota = await self.history_repository.increment_user_credit_usage(
                self.session.owner_id,
                credits,
            )
            await self._send_json(self._quota_update_payload(quota))
        except Exception:
            logger.exception("Failed to charge screenshot credits for session %s", self.session.id)

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
            await self.history_repository.refresh_session_handoff(
                self.session.id,
                owner_id=self.session.owner_id,
                resume_state=status,
            )
            stored_session = await self.history_repository.get_session(self.session.id)
            if stored_session and stored_session.context_packet:
                await self._emit_context_packet(
                    stage="refreshed",
                    packet=stored_session.context_packet,
                )
        except Exception:
            logger.exception("Failed to update Firestore summary for session %s", self.session.id)

    @staticmethod
    def _clip_text(value: Any, limit: int = 240) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    @staticmethod
    def _serialize_datetime(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return value.isoformat()
        except Exception:
            return None

    def _run_payload(self, run: Any | None = None, *, status: str | None = None) -> dict[str, Any]:
        if run is not None:
            return {
                "run_id": run.run_id,
                "session_id": run.session_id,
                "owner_id": run.owner_id,
                "status": run.status,
                "created_at": self._serialize_datetime(run.created_at),
                "updated_at": self._serialize_datetime(run.updated_at),
                "started_at": self._serialize_datetime(run.started_at),
                "completed_at": self._serialize_datetime(run.completed_at),
                "last_step_at": self._serialize_datetime(run.last_step_at),
                "step_count": run.step_count,
                "artifact_count": run.artifact_count,
                "title": run.title,
                "source_session_id": run.source_session_id,
            }
        return {
            "run_id": self._current_run_id,
            "session_id": self.session.id,
            "owner_id": self.session.owner_id,
            "status": status or self.session.run_status,
            "created_at": None,
            "updated_at": None,
            "started_at": None,
            "completed_at": None,
            "last_step_at": None,
            "step_count": 0,
            "artifact_count": self.session.artifact_count,
            "title": self.session.initial_title,
            "source_session_id": self.session.resume_source_session_id,
        }

    def _step_payload(self, step: Any) -> dict[str, Any]:
        return {
            "step_id": step.step_id,
            "run_id": step.run_id,
            "session_id": step.session_id,
            "step_type": step.step_type,
            "status": step.status,
            "title": step.title,
            "detail": step.detail,
            "created_at": self._serialize_datetime(step.created_at),
            "updated_at": self._serialize_datetime(step.updated_at),
            "completed_at": self._serialize_datetime(step.completed_at),
            "step_index": step.step_index,
            "source": step.source,
            "error": step.error,
            "external_ref": step.external_ref,
            "metadata": step.metadata or {},
        }

    def _artifact_payload(self, artifact: Any) -> dict[str, Any]:
        return {
            "artifact_id": artifact.artifact_id,
            "run_id": artifact.run_id,
            "session_id": artifact.session_id,
            "kind": artifact.kind,
            "title": artifact.title,
            "preview": artifact.preview,
            "created_at": self._serialize_datetime(artifact.created_at),
            "source_step_id": artifact.source_step_id,
            "path": artifact.path,
            "url": artifact.url,
            "metadata": artifact.metadata or {},
        }

    def _bind_workspace_context(self) -> None:
        if not self._current_run_id:
            return
        self._workspace_path = derive_workspace_path(self.session.id, self._current_run_id)
        set_run_id(self._current_run_id)
        set_workspace_path(self._workspace_path)

    async def _prepare_workspace_for_turn(self, task_summary: str) -> None:
        if not self._current_run_id:
            return
        self._bind_workspace_context()
        if not await self._ensure_session_workspace_root():
            logger.warning(
                "Proceeding with per-run workspace preparation even though session root %s "
                "could not be pre-created for session %s",
                derive_session_workspace_path(self.session.id),
                self.session.id,
            )
        step_id = await self._create_step(
            step_type="workspace_sync",
            title="Workspace prepared",
            detail="Preparing run workspace and task files.",
            source="system",
            metadata={"workspace_path": self._workspace_path or ""},
        )
        try:
            result = await prepare_task_workspace(task_summary)
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            detail = (
                f"Workspace ready at {result['workspace_path']}."
                if not result.get("created")
                else f"Created workspace at {result['workspace_path']}."
            )
            touched_files = result.get("touched_files") or []
            if touched_files:
                detail += f" Updated: {', '.join(str(name) for name in touched_files)}."
            await self._complete_step(
                step_id,
                detail=detail,
                metadata={
                    "workspace_path": result.get("workspace_path"),
                    "touched_files": touched_files,
                    "created": bool(result.get("created")),
                },
            )
        except Exception as exc:
            await self._fail_step(
                step_id,
                detail="Failed to prepare the run workspace.",
                error=str(exc),
                metadata={"workspace_path": self._workspace_path or ""},
            )
            raise

    async def _save_final_response(self, text: str) -> None:
        if not text.strip() or not self._current_run_id:
            return
        try:
            self._bind_workspace_context()
            result = await write_workspace_file("outputs/final.md", text, append=False)
            output_path = result.get("output_path")
            if isinstance(output_path, str) and output_path:
                await self._create_artifact(
                    kind="workspace_output",
                    title="final.md",
                    preview=self._clip_text(text, 280),
                    source_step_id=self._current_turn_step_id,
                    path=output_path,
                    metadata={
                        "workspace_path": self._workspace_path or "",
                        "workspace_relative_path": "outputs/final.md",
                        "source": "final_response",
                    },
                )
        except Exception:
            logger.exception("Failed to save final response into the workspace")

    async def _ensure_session_workspace_root(self) -> bool:
        session_workspace_path = derive_session_workspace_path(self.session.id)
        loop = asyncio.get_running_loop()
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                await loop.run_in_executor(
                    None,
                    self.session.sandbox.ensure_directory,
                    session_workspace_path,
                )
                return True
            except Exception as exc:
                last_exc = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                logger.warning(
                    "Workspace root creation attempt %s/3 failed for session %s at %s: %s",
                    attempt,
                    self.session.id,
                    session_workspace_path,
                    exc,
                )
                if attempt < 3:
                    await asyncio.sleep(0.5)

        logger.error(
            "Failed to prepare session workspace root %s for session %s after 3 attempts",
            session_workspace_path,
            self.session.id,
            exc_info=last_exc,
        )
        return False

    async def _set_run_status(self, status: str) -> None:
        self.session.run_status = status
        if not self.history_repository or not self._current_run_id:
            await self._send_json({
                "type": "run_status",
                "run": self._run_payload(status=status),
            })
            return
        try:
            run = await self.history_repository.set_run_status(
                session_id=self.session.id,
                run_id=self._current_run_id,
                status=status,
            )
            if run:
                self.session.run_status = run.status
                self.session.artifact_count = run.artifact_count
            await self._send_json({
                "type": "run_status",
                "run": self._run_payload(run, status=status),
            })
        except Exception:
            logger.exception("Failed to update run status for session %s", self.session.id)

    async def _create_step(
        self,
        *,
        step_type: str,
        title: str,
        detail: str = "",
        source: str | None = None,
        external_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self.history_repository or not self._current_run_id:
            return None
        try:
            step = await self.history_repository.create_step(
                session_id=self.session.id,
                run_id=self._current_run_id,
                step_type=step_type,
                title=title,
                detail=detail,
                source=source,
                external_ref=external_ref,
                metadata=metadata,
            )
            await self._send_json({"type": "step_started", "step": self._step_payload(step)})
            return step.step_id
        except Exception:
            logger.exception("Failed to create %s step for session %s", step_type, self.session.id)
            return None

    async def _complete_step(
        self,
        step_id: str | None,
        *,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not step_id or not self.history_repository or not self._current_run_id:
            return
        try:
            step = await self.history_repository.complete_step(
                session_id=self.session.id,
                run_id=self._current_run_id,
                step_id=step_id,
                detail=detail,
                metadata=metadata,
            )
            if step:
                await self._send_json({"type": "step_completed", "step": self._step_payload(step)})
        except Exception:
            logger.exception("Failed to complete step %s for session %s", step_id, self.session.id)

    async def _fail_step(
        self,
        step_id: str | None,
        *,
        detail: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "failed",
    ) -> None:
        if not step_id or not self.history_repository or not self._current_run_id:
            return
        try:
            step = await self.history_repository.fail_step(
                session_id=self.session.id,
                run_id=self._current_run_id,
                step_id=step_id,
                detail=detail,
                error=error,
                metadata=metadata,
                status=status,
            )
            if step:
                await self._send_json({"type": "step_failed", "step": self._step_payload(step)})
        except Exception:
            logger.exception("Failed to fail step %s for session %s", step_id, self.session.id)

    async def _fail_unfinished_tool_steps(self, *, status: str, error: str | None = None) -> None:
        pending = [step_id for step_ids in self._tool_step_ids.values() for step_id in step_ids]
        self._tool_step_ids = {}
        for step_id in pending:
            await self._fail_step(
                step_id,
                detail=error or "Tool step did not complete.",
                error=error,
                status=status,
            )

    async def _create_artifact(
        self,
        *,
        kind: str,
        title: str,
        preview: str,
        source_step_id: str | None = None,
        path: str | None = None,
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.history_repository or not self._current_run_id:
            return
        try:
            artifact = await self.history_repository.create_artifact(
                session_id=self.session.id,
                run_id=self._current_run_id,
                kind=kind,
                title=title,
                preview=preview,
                source_step_id=source_step_id,
                path=path,
                url=url,
                metadata=metadata,
            )
            self.session.artifact_count += 1
            await self.history_repository.refresh_session_handoff(
                self.session.id,
                owner_id=self.session.owner_id,
                resume_state=self.session.run_status,
            )
            await self._send_json({
                "type": "artifact_created",
                "artifact": self._artifact_payload(artifact),
            })
        except Exception:
            logger.exception("Failed to create artifact for session %s", self.session.id)

    async def _on_permission_requested(self, task: BackgroundTask) -> str | None:
        return await self._create_step(
            step_type="permission_request",
            title=task.description,
            detail=f"Awaiting approval for a background task ({task.estimated_seconds}s estimate).",
            source=task.agent,
            external_ref=task.task_id,
            metadata={"estimated_seconds": task.estimated_seconds},
        )

    async def _on_permission_resolved(self, task: BackgroundTask, approved: bool) -> None:
        if approved:
            await self._complete_step(
                task.permission_step_id,
                detail="Permission granted.",
                metadata={"approved": True},
            )
            return
        await self._fail_step(
            task.permission_step_id,
            detail="Permission denied or timed out.",
            error="Permission denied or timed out.",
            metadata={"approved": False},
            status="cancelled",
        )

    async def _on_background_task_started(self, task: BackgroundTask) -> str | None:
        return await self._create_step(
            step_type="background_task",
            title=task.description,
            detail="Background task started.",
            source=task.agent,
            external_ref=task.task_id,
            metadata={"estimated_seconds": task.estimated_seconds},
        )

    async def _on_background_task_finished(self, task: BackgroundTask, success: bool, result: str) -> None:
        if success:
            await self._complete_step(
                task.background_step_id,
                detail=self._clip_text(result, 1000),
            )
            return
        await self._fail_step(
            task.background_step_id,
            detail=self._clip_text(result, 1000),
            error=self._clip_text(result, 500),
            status="cancelled" if "cancel" in result.lower() else "failed",
        )

    def _extract_reference_artifact(
        self,
        tool_name: str,
        output_mapping: dict[str, Any],
        output_str: str,
    ) -> dict[str, Any] | None:
        if tool_name == "take_screenshot":
            description = output_mapping.get("description") if isinstance(output_mapping.get("description"), str) else output_str
            return {
                "kind": "screenshot_reference",
                "title": "Screenshot capture",
                "preview": self._clip_text(description, 280),
                "metadata": {"tool": tool_name},
            }

        for key in ("path", "file_path", "output_path", "url", "download_url"):
            value = output_mapping.get(key)
            if isinstance(value, str) and value.strip():
                return {
                    "kind": "export_reference",
                    "title": tool_name.replace("_", " "),
                    "preview": self._clip_text(output_str or value, 280),
                    "path": value if "path" in key else None,
                    "url": value if "url" in key else None,
                    "metadata": {"tool": tool_name, "ref_key": key},
                }
        return None
