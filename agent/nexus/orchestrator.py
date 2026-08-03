# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Orchestrator — wires voice → agent → sandbox → vision → response."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import httpx
from google.adk.events import Event
from google.genai import types
from starlette.websockets import WebSocket, WebSocketState

from nexus.agent import (
    AgentTurnResult,
    create_planner_agent,
    create_runner,
    run_agent_turn,
)
from nexus.background_tasks import BackgroundTask, BackgroundTaskManager
from nexus.billing import calculate_screenshot_credits, calculate_usage_credits
from nexus.history_repository import FirestoreHistoryRepository
from nexus.mcp_client import build_mcp_adk_tools, redact_sensitive
from nexus.runtime_config import SessionRuntimeConfig
from nexus.sandbox import SandboxDeadError
from nexus.skills import build_enabled_skills_prompt
from nexus.tools._context import (
    reset_worker_call_count,
    set_artifact_callback,
    set_ask_user_callback,
    set_bg_task_manager,
    set_ensure_sandbox_callback,
    set_history_repository,
    set_owner_id,
    set_production_task_repository,
    set_run_id,
    set_runtime_config,
    set_sandbox,
    set_send_json,
    set_session_id,
    set_subagent_resource_locks,
    set_subagent_supervisor,
    set_task_id,
    set_workspace_path,
    get_task_budget_guard,
)
from nexus.config import settings
from nexus.output_normalization import classify_part, sanitize_stream_text
from nexus.control_loop import (
    ActionDecision,
    ActionLedger,
    ActionObservation,
    CompletionVerification,
    verify_completion,
)
from nexus.context_builder import (
    PRIORITY_MEMORY,
    PRIORITY_RESUME,
    PRIORITY_TURN,
    TurnContextBuilder,
)
from nexus.debug_trace import emit_debug_trace
from nexus.event_sink import (
    CompositeEventSink,
    build_session_event_sink,
    prepare_correlated_event,
)
from nexus.prompts.system import SYSTEM_PROMPT, VOICE_SYSTEM_PROMPT
from nexus.tools.workspace import (
    derive_session_workspace_path,
    derive_workspace_path,
    prepare_task_workspace,
    reconcile_todo_list_at_turn_end,
    write_workspace_file,
)
from nexus.usage import TokenUsageRecord, extract_token_usage_records
from nexus.tracing import (
    TraceContext,
    monotonic_ms,
    new_step_id,
    new_trace_id,
    result_status,
    safe_trace_value,
    set_trace_context,
)


_RESUME_CONTEXT_MODES = frozenset({"continue_latest_workspace", "continue_conversation"})


if TYPE_CHECKING:
    from nexus.production_tasks import ProductionTaskRepository
    from nexus.session import Session

logger = logging.getLogger(__name__)


# Nudge sent when the model gathered evidence but produced no closing text and
# completion verification returned a retryable MISSING_FINAL_RESPONSE.
_FINAL_SYNTHESIS_NUDGE = (
    "You have already gathered the information needed. Do NOT call any tools. "
    "Write the final answer or summary for the user now, using only what has "
    "already been collected."
)


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
        production_task_repository: "ProductionTaskRepository | None" = None,
        ensure_sandbox_ready: Callable[[], Awaitable[None]] | None = None,
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
        self.production_task_repository = production_task_repository
        self._ensure_sandbox_ready_callback = ensure_sandbox_ready
        self._sandbox_ready_reported = bool(session.stream_url)
        self._current_run_id = session.current_run_id
        self._durable_task_id = self._resolve_durable_task_id()
        self._durable_run_id = self._resolve_durable_run_id()
        self._trace_context = TraceContext(
            trace_id=new_trace_id(self._current_run_id or ""),
            run_id=self._current_run_id or "",
            provider=settings.model_provider,
            model=settings.planner_model,
        )
        set_trace_context(self._trace_context)
        self._event_sink: CompositeEventSink = build_session_event_sink(
            repository=production_task_repository if self._durable_task_id else None,
            send_json=self._send_json_to_ws,
            task_id=self._durable_task_id,
            owner_id=session.owner_id,
            run_id=self._durable_run_id,
        )

        # Only create voice manager when Gemini credentials are available
        if self.runtime_config.gemini_available:
            from nexus.voice import GeminiLiveManager, VoiceConnectionError
            self.voice = GeminiLiveManager(self.runtime_config)
            self._voice_connection_error_cls = VoiceConnectionError

        # ADK agent + runner: one production planner path.
        self._integration_tools: list = []
        self._skill_instruction: str = ""
        self._active_task_model = (
            getattr(self.runtime_config, "qwen_planner_model", "")
            or settings.planner_model
        )
        self._agent = create_planner_agent(self.runtime_config)
        logger.info("Using planner V2 mode (AgentTool workers)")
        self._runner, self._session_service = create_runner(self._agent)
        from nexus.subagents import SubagentSupervisor
        from nexus.subagent_store import FirestoreSubagentRepository

        subagent_repository = None
        if (
            settings.durable_subagents_enabled
            and isinstance(history_repository, FirestoreHistoryRepository)
        ):
            subagent_repository = FirestoreSubagentRepository(
                db=history_repository._db
            )

        self._subagent_supervisor = SubagentSupervisor(
            runtime_config=self.runtime_config,
            session_service=self._session_service,
            owner_id=session.owner_id,
            parent_session_id=session.id,
            parent_run_id=self._current_run_id,
            parent_task_id=self._durable_task_id,
            history_repository=history_repository,
            subagent_repository=subagent_repository,
            send_json=self._send_json,
            usage_callback=self._persist_token_usage,
        )
        self._adk_session_id: str | None = None
        self._user_id = session.owner_id
        self._active_agent: str = "nexus_orchestrator"

        # Background task manager
        self.bg_task_manager = BackgroundTaskManager(send_json=self._send_json)
        self.bg_task_manager.set_callbacks(
            on_permission_requested=self._on_permission_requested,
            on_permission_resolved=self._on_permission_resolved,
            on_task_started=self._on_background_task_started,
            on_task_finished=self._on_background_task_finished,
        )
        self._current_turn_step_id: str | None = None
        self._tool_step_ids: dict[str, list[str]] = {}
        self._tool_trace_steps: dict[str, list[dict[str, Any]]] = {}
        # Correlate tool results to their originating call by function-call id
        # (robust when the same tool is invoked multiple times in one turn).
        # Falls back to the tool_name FIFO maps above when an id is absent.
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}
        self._current_thinking: str = ""
        # Compact-reasoning: whether a "Thinking..." status was already emitted
        # for the current reasoning burst (reset per turn and per tool phase).
        self._reasoning_status_emitted: bool = False
        self._action_ledger = ActionLedger()
        self.last_turn_result: dict[str, Any] | None = None
        self._resume_checkpoint: dict[str, Any] = {}

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
        # ask_user: question_id -> future resolved by the user's ws reply
        self._pending_user_questions: dict[str, asyncio.Future] = {}
        # WebSocket I/O is delegated to a bound collaborator (built lazily so
        # instances created via __new__ in tests still resolve it).
        self._delegates = None

    def _ensure_delegates(self):
        delegates = self.__dict__.get("_delegates")
        if delegates is None:
            from nexus.orchestrator_collaborators import WsMessenger

            self._ws_messenger = WsMessenger(self)
            delegates = (self._ws_messenger,)
            self._delegates = delegates
        return delegates

    def __getattr__(self, name: str):
        # Only invoked for methods moved to a bound collaborator (e.g. the
        # WebSocket send layer). Class-level lookup avoids triggering the
        # collaborator's own __getattr__ and any recursion.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        for delegate in self._ensure_delegates():
            if getattr(type(delegate), name, None) is not None:
                return getattr(delegate, name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def _debug_run_id(self) -> str:
        return getattr(self, "_current_run_id", None) or f"live:{id(self):x}"

    def restore_durable_checkpoint(self, checkpoint: dict[str, Any] | None) -> None:
        """Restore persisted control-loop state before a reclaimed run starts."""
        self._resume_checkpoint = dict(checkpoint or {})

    async def initialize(self, *, lazy_sandbox: bool = False) -> None:
        """Set up ADK session. Voice connection is deferred until user starts mic."""
        # region agent log
        emit_debug_trace(
            run_id=self._debug_run_id(),
            hypothesis_id="H1,H2,H3,H5",
            location="orchestrator.py:190",
            message="orchestrator_initialized",
            data={
                "planner_mode": "planner_v2",
                "model_provider": settings.model_provider,
                "planner_model": settings.planner_model,
                "worker_model": settings.worker_model,
                "task_worker_enabled": settings.task_worker_enabled,
                "durable_run_bound": bool(self._durable_task_id),
                "sandbox_alive": bool(getattr(self.session.sandbox, "is_alive", False)),
                "e2b_key_available": bool(self.runtime_config.e2b_api_key),
                "gemini_available": self.runtime_config.gemini_available,
            },
        )
        # endregion agent log
        # Bind sandbox and bg task manager to tool context
        set_sandbox(self.session.sandbox)
        set_bg_task_manager(self.bg_task_manager)
        set_runtime_config(self.runtime_config)
        set_session_id(self.session.id)
        set_owner_id(self.session.owner_id)
        set_history_repository(self.history_repository)
        set_production_task_repository(self.production_task_repository)
        set_task_id(self._durable_task_id)
        set_send_json(self._send_json)
        set_artifact_callback(self._send_artifact_created)
        set_subagent_supervisor(self._subagent_supervisor)
        set_subagent_resource_locks(self._subagent_supervisor.resource_locks)
        set_ensure_sandbox_callback(lambda: self._ensure_sandbox_ready("tool_use"))
        set_ask_user_callback(self._ask_user_and_wait)
        self._bind_workspace_context()
        if not lazy_sandbox:
            workspace_root_ready = await self._ensure_session_workspace_root()
            if not workspace_root_ready:
                logger.warning(
                    "Continuing session %s initialization without a prepared workspace root",
                    self.session.id,
                )

        await self._load_integration_tools()

        # Voice is NOT connected here — deferred until start_voice() is called
        if self.voice:
            logger.info("Voice available — waiting for user to start mic")
        else:
            logger.info("No Google credentials — voice disabled, text input works")

        await self._ensure_adk_session()
        await self._subagent_supervisor.recover_for_run()

        # Only explicit continuation modes may hydrate durable context. A fresh
        # session must never inherit a previous task's errors or instructions.
        if self.history_repository and self._should_load_cached_context(self.session.resume_mode):
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
        elif self.history_repository:
            logger.info("Skipping cached context for fresh session %s", self.session.id)

        # Notify frontend
        await self._send_json({
            "type": "sandbox_status",
            "status": "ready" if self.session.sandbox.is_alive else "idle",
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

    def _resolve_durable_task_id(self) -> str | None:
        task_id = str(getattr(self.session, "task_id", "") or "").strip()
        return task_id if task_id.startswith("task_") else None

    def _resolve_durable_run_id(self) -> str | None:
        run_id = str(getattr(self.session, "current_run_id", "") or "").strip()
        return run_id if run_id.startswith("run_") else None

    def bind_durable_run(self, *, task_id: str, run_id: str) -> None:
        """Attach this live orchestrator to a durable task/run."""
        self.session.task_id = task_id
        self.session.current_run_id = run_id
        self._current_run_id = run_id
        self._durable_task_id = self._resolve_durable_task_id()
        self._durable_run_id = self._resolve_durable_run_id()
        self._trace_context = TraceContext(
            trace_id=new_trace_id(run_id),
            run_id=run_id,
            provider=settings.model_provider,
            model=settings.planner_model,
        )
        set_trace_context(self._trace_context)
        self._event_sink = build_session_event_sink(
            repository=self.production_task_repository if self._durable_task_id else None,
            send_json=self._send_json_to_ws,
            task_id=self._durable_task_id,
            owner_id=self.session.owner_id,
            run_id=self._durable_run_id,
        )
        set_task_id(self._durable_task_id)
        self._subagent_supervisor.update_parent_run(self._current_run_id)
        self._subagent_supervisor.update_parent_task(self._durable_task_id)
        try:
            asyncio.get_running_loop().create_task(
                self._subagent_supervisor.recover_for_run()
            )
        except RuntimeError:
            pass
        self._bind_workspace_context()
        # History child writes need sessions/{id}/runs/{run_id}. Durable
        # production_tasks runs do not create that doc — schedule ensure.
        if self.history_repository and run_id:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._ensure_history_run(run_id, task_id=task_id))
            except RuntimeError:
                pass

    async def _ensure_history_run(self, run_id: str, *, task_id: str | None = None) -> None:
        """Make sure the history run doc exists before steps/artifacts write."""
        if not self.history_repository:
            return
        try:
            await self.history_repository.ensure_run(
                session_id=self.session.id,
                run_id=run_id,
                owner_id=self.session.owner_id,
                title=getattr(self.session, "initial_title", None) or "Agent Turn",
                task_id=task_id or getattr(self.session, "task_id", None),
                status=getattr(self.session, "run_status", None) or "queued",
            )
        except Exception:
            logger.exception(
                "Failed to ensure history run %s for session %s",
                run_id,
                self.session.id,
            )

    async def start_desktop(self) -> None:
        """Start or resume the sandbox because the user opened the desktop."""
        await self._ensure_sandbox_ready("desktop")

    async def _load_integration_tools(self) -> None:
        """Load enabled per-user skills and MCP tools into the ADK runner."""
        if not self.history_repository:
            return
        try:
            user_settings = await self.history_repository.get_user_settings(self.session.owner_id)
            connections = await self.history_repository.list_enabled_integration_connections(
                self.session.owner_id
            )
            self._integration_tools = build_mcp_adk_tools(connections)
            self._integration_tools.extend(self._native_connector_tools(connections))

            # Extract MCP tool metadata for the skill prompt so the LLM knows
            # which external tools are available.
            mcp_tool_meta: list[dict[str, Any]] = []
            for conn in connections:
                if conn.connector_type == "mcp_remote_http" and conn.private.get("tools"):
                    for tool_info in conn.private["tools"]:
                        tool_name = tool_info.get("name", "")
                        params_obj = tool_info.get("parameters") or {}
                        props = params_obj.get("properties", {}) if isinstance(params_obj, dict) else {}
                        param_names = ", ".join(props.keys()) if isinstance(props, dict) else ""
                        mcp_tool_meta.append({"name": tool_name, "parameters": param_names})

            self._skill_instruction = build_enabled_skills_prompt(
                user_settings, mcp_tools=mcp_tool_meta or None
            )
        except Exception:
            logger.warning("Failed to load integration tools for session %s", self.session.id, exc_info=True)
            self._integration_tools = []

        self._rebuild_runner()
        if self._integration_tools:
            logger.info(
                "Loaded %d MCP integration tools for session %s",
                len(self._integration_tools),
                self.session.id,
            )

    @staticmethod
    def _native_connector_tools(connections: list) -> list:
        """Native SaaS tools injected only when the matching connector is connected.

        Keeps the planner's default tool surface small (docs/AGENT_V2_PLAN.md §4).
        """
        providers = {
            str(getattr(conn, "provider", "") or "").lower() for conn in connections
        }
        tools: list = []
        if any(p.startswith("google") or p in {"gmail"} for p in providers):
            from nexus.tools.integrations import (
                calendar_create,
                calendar_list,
                create_drive_doc,
                gmail_read,
                gmail_search,
                gmail_send,
                read_drive_file,
                search_drive,
                tasks_create,
                tasks_list,
                upload_drive_file,
            )

            tools.extend([
                search_drive, read_drive_file, create_drive_doc, upload_drive_file,
                gmail_search, gmail_read, gmail_send,
                tasks_list, tasks_create, calendar_list, calendar_create,
            ])
        if "github" in providers:
            from nexus.tools.integrations import (
                github_create_issue,
                github_list_issues,
                github_read_file,
                github_search_repos,
                github_summarize_pr,
            )

            tools.extend([
                github_search_repos, github_read_file, github_list_issues,
                github_create_issue, github_summarize_pr,
            ])
        if "tinyfish" in providers:
            from nexus.tools.integrations import tinyfish_web_agent

            tools.append(tinyfish_web_agent)
        return tools

    def _rebuild_runner(self) -> None:
        kwargs = {
            "integration_tools": self._integration_tools,
            "skill_instruction": self._skill_instruction,
        }
        self._agent = create_planner_agent(self.runtime_config, **kwargs)
        self._runner, self._session_service = create_runner(
            self._agent,
            session_service=self._session_service,
        )
        self._subagent_supervisor.runtime_config = self.runtime_config
        self._subagent_supervisor.session_service = self._session_service

    def _select_turn_runner(self):
        """Return the single planner runner + default turn cap.

        The former per-mode selection (artifact / deep / work) and fast-path
        gating were removed in the full-agent-only migration — every turn now
        goes through the planner. See ``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``.
        """
        return self._runner, settings.max_agent_turns

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

    async def handle_text_input(
        self,
        text: str,
        connector_ids: list[str] | None = None,
        tool_ids: list[str] | None = None,
        uploaded_files: list[dict[str, Any]] | None = None,
        emit_user_transcript: bool = True,
        resume_context: str | None = None,
    ) -> None:
        """Handle direct text input (bypass voice).

        The visible/persisted user message is always ``text`` (the original
        request). ``resume_context`` (e.g. a durable-resume checkpoint block)
        is fed to the model only and is never shown or persisted, so internal
        directives cannot leak into the chat as a user bubble.
        """
        original_request = text
        if emit_user_transcript:
            await self._send_json({"type": "transcript", "role": "user", "text": text})

        trimmed = text.strip()
        if trimmed.startswith("/"):
            parts = trimmed.split(maxsplit=1)
            command = parts[0][1:]
            from nexus.skills import list_agent_skills
            user_settings = await self.history_repository.get_user_settings(self.session.owner_id)
            skills = list_agent_skills(user_settings)
            matching_skill = next((s for s in skills if s["skill_id"] == command and s["enabled"]), None)
            if matching_skill:
                text = (
                    f"[SYSTEM DIRECTIVE: User has explicitly triggered skill '{matching_skill['name']}'. "
                    f"You MUST call read_skill('{command}') as your very first step to load its custom instructions, "
                    f"then apply them to solve the user prompt: '{parts[1] if len(parts) > 1 else ''}']\n\n"
                    f"User request: {text}"
                )

        # Parse tool mentions in format @[tool_id] or @tool_id
        import re
        matches = re.findall(r"@(?:\[([^\]]+)\]|(\w+))", text)
        mentioned_tools = [m[0] or m[1] for m in matches if m[0] or m[1]]
        if mentioned_tools:
            directives = []
            for tool in mentioned_tools:
                directives.append(
                    f"User has explicitly requested tool '{tool}'. "
                    f"You MUST call '{tool}' as part of your execution plan to satisfy the request."
                )
            directive_prompt = "[SYSTEM DIRECTIVES:\n" + "\n".join(directives) + "]\n\n"
            text = directive_prompt + text

        if emit_user_transcript:
            await self._persist_message(role="user", source="typed", text=original_request)

        model_text = text
        if resume_context:
            model_text = f"{text}\n\n{resume_context}"
        await self._run_agent_tracked(
            await self._build_turn_input(
                model_text,
                connector_ids=connector_ids,
                tool_ids=tool_ids,
                uploaded_files=uploaded_files,
            ),
            source="typed",
            completion_request=original_request,
            connector_ids=connector_ids,
            tool_ids=tool_ids,
        )

    def handle_permission_response(self, task_id: str, approved: bool) -> None:
        """Route a permission_response from the frontend to the bg task manager."""
        self.bg_task_manager.handle_permission_response(task_id, approved)

    async def _ask_user_and_wait(self, question: str) -> str | None:
        """ask_user tool callback: surface a question card and await the reply."""
        import uuid as _uuid

        question_id = f"q_{_uuid.uuid4().hex[:10]}"
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_user_questions[question_id] = future

        await self._send_json({
            "type": "user_question",
            "question_id": question_id,
            "question": question,
            "timeout_seconds": settings.ask_user_timeout_seconds,
        })
        await self._persist_message(role="agent", source="ask_user", text=question)
        step_id = await self._create_step(
            step_type="ask_user",
            title="Waiting for your answer",
            detail=question,
            source=getattr(self, "_active_agent", "nexus_planner"),
            metadata={"question_id": question_id, "question": question},
        )

        try:
            answer = await self._await_question_answer(question_id, future)
        except asyncio.TimeoutError:
            await self._fail_step(
                step_id,
                detail="No answer before timeout.",
                error="ask_user timed out",
                status="cancelled",
            )
            await self._send_json({
                "type": "user_question_resolved",
                "question_id": question_id,
                "answered": False,
            })
            return None
        finally:
            self._pending_user_questions.pop(question_id, None)

        answer_text = str(answer or "").strip()
        await self._persist_message(role="user", source="ask_user_response", text=answer_text)
        await self._complete_step(
            step_id,
            detail=f"Q: {question}\nA: {answer_text}",
            metadata={"question_id": question_id, "answer": answer_text},
        )
        await self._send_json({
            "type": "user_question_resolved",
            "question_id": question_id,
            "answered": True,
        })
        return answer_text

    def handle_user_question_response(self, question_id: str, answer: str) -> None:
        """Resolve a pending ask_user future from a frontend reply."""
        future = self._pending_user_questions.get(str(question_id or "").strip())
        if future is None or future.done():
            logger.info("Ignoring stale user_question_response %s", question_id)
            return
        future.set_result(str(answer or ""))

    async def _await_question_answer(self, question_id: str, future: asyncio.Future) -> str:
        """Wait for an ask_user answer via the live WS future or the durable event log.

        Durable (worker-owned) runs have no live WebSocket: the user's reply
        lands as a ``user_question_response`` event on the durable task, so we
        poll the event log alongside the in-process future.
        """
        timeout = settings.ask_user_timeout_seconds
        if not (self._durable_task_id and self.production_task_repository is not None):
            return await asyncio.wait_for(future, timeout=timeout)

        deadline = asyncio.get_running_loop().time() + timeout
        last_seq = 0
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            try:
                return await asyncio.wait_for(
                    asyncio.shield(future), timeout=min(2.0, remaining)
                )
            except asyncio.TimeoutError:
                pass
            try:
                events = await self.production_task_repository.list_events(
                    task_id=self._durable_task_id,
                    owner_id=self.session.owner_id,
                    after_seq=last_seq,
                    limit=100,
                )
            except Exception:
                logger.debug("Durable question poll failed", exc_info=True)
                continue
            for event in events:
                last_seq = max(last_seq, int(getattr(event, "seq", 0) or 0))
                if getattr(event, "event_type", "") != "user_question_response":
                    continue
                payload = getattr(event, "payload", None) or {}
                if str(payload.get("question_id") or "") == question_id:
                    return str(payload.get("answer") or "")

    async def handle_user_utterance(self, text: str) -> None:
        """Called when Gemini Live produces a final user transcript."""
        await self._send_json({"type": "transcript", "role": "user", "text": text})
        await self._persist_message(role="user", source="voice", text=text)
        await self._run_agent_tracked(
            await self._build_turn_input(text),
            source="voice",
            completion_request=text,
        )

    async def handle_analyze_screen(self) -> None:
        """Take screenshot and send analysis to frontend."""
        if not await self._ensure_sandbox_ready("screen_analysis"):
            await self._send_json({
                "type": "agent_screenshot",
                "error": "Sandbox is not running and could not be started.",
            })
            return
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
            metadata={"source": "manual_screen_analysis", "role": "source"},
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

    def has_active_agent_turn(self) -> bool:
        """Return True while a user task is still executing."""
        return bool(self._agent_task and not self._agent_task.done())

    # ── Private ────────────────────────────────────────────────

    _RATE_LIMIT_MAX_RETRIES = 4
    _RATE_LIMIT_BASE_WAIT = 10.0  # seconds; doubles each attempt: 10, 20, 40, 80
    _RATE_LIMIT_PATTERNS = ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "too many requests")
    _ADK_REPLAY_TURN_LIMIT = 15
    _RESUME_PACKET_SOFT_TOKENS = 2_000
    _RESUME_PACKET_HARD_TOKENS = 3_200

    async def _ensure_adk_session(self) -> None:
        """Reuse the stable ADK session, rebuilding it from Firestore history if absent."""
        adk_session_id = self.session.id
        adk_session = await self._session_service.get_session(
            app_name="nexus",
            user_id=self._user_id,
            session_id=adk_session_id,
        )
        if adk_session is None:
            adk_session = await self._session_service.create_session(
                app_name="nexus",
                user_id=self._user_id,
                session_id=adk_session_id,
            )
            await self._replay_firestore_messages_into_adk(adk_session)

        self._adk_session_id = adk_session.id

    async def _replay_firestore_messages_into_adk(self, adk_session) -> None:
        """Seed a newly-created ADK session with the last stored conversation turns."""
        if not self.history_repository:
            return
        try:
            messages = await self.history_repository.get_session_messages(self.session.id)
        except Exception:
            logger.warning("Failed to read Firestore messages for ADK replay", exc_info=True)
            return

        replay_messages = self._select_messages_for_adk_replay(
            messages,
            turn_limit=self._ADK_REPLAY_TURN_LIMIT,
        )
        for message in replay_messages:
            event = self._message_to_adk_event(message)
            if event is None:
                continue
            await self._session_service.append_event(adk_session, event)

        if replay_messages:
            logger.info(
                "Replayed %d Firestore message(s) into ADK session %s for user %s",
                len(replay_messages),
                self.session.id,
                self._user_id,
            )

    @staticmethod
    def _select_messages_for_adk_replay(
        messages: list[dict[str, Any]],
        *,
        turn_limit: int,
    ) -> list[dict[str, Any]]:
        normalized = [
            message
            for message in messages
            if message.get("role") in {"user", "agent"} and str(message.get("text") or "").strip()
        ]
        if not normalized:
            return []

        selected_reversed: list[dict[str, Any]] = []
        user_turns = 0
        for message in reversed(normalized):
            selected_reversed.append(message)
            if message.get("role") == "user":
                user_turns += 1
                if user_turns >= turn_limit:
                    break

        return list(reversed(selected_reversed))

    def _message_to_adk_event(self, message: dict[str, Any]) -> Event | None:
        role = message.get("role")
        text = str(message.get("text") or "").strip()
        if not text:
            return None
        if role == "user":
            author = "user"
            content_role = "user"
        elif role == "agent":
            author = getattr(self._agent, "name", None) or self._active_agent or "nexus"
            content_role = "model"
        else:
            return None

        event_id = str(message.get("id") or message.get("turnIndex") or "")
        return Event(
            author=author,
            invocation_id=f"replay-{self.session.id}",
            id=f"firestore-{event_id}" if event_id else "",
            content=types.Content(
                role=content_role,
                parts=[types.Part(text=text)],
            ),
        )

    def _is_rate_limit_error(self, exc: BaseException) -> bool:
        msg = str(exc).lower()
        return any(p.lower() in msg for p in self._RATE_LIMIT_PATTERNS)

    def _task_model_candidates(self) -> tuple[str, ...]:
        from nexus.model_select import model_candidates

        return model_candidates("planner", self.runtime_config)

    def _rate_limit_source_label(self) -> str:
        return "Qwen/DashScope"

    def _rebuild_agent_for_task_model(self, task_model: str) -> None:
        if task_model == self._active_task_model:
            return

        self.runtime_config = replace(
            self.runtime_config,
            qwen_planner_model=task_model,
        )
        self.session.runtime_config = self.runtime_config
        set_runtime_config(self.runtime_config)

        kwargs = {
            "integration_tools": self._integration_tools,
            "skill_instruction": self._skill_instruction,
        }
        self._agent = create_planner_agent(
            self.runtime_config,
            task_model_override=task_model,
            **kwargs,
        )
        self._runner, self._session_service = create_runner(
            self._agent,
            session_service=self._session_service,
        )
        self._subagent_supervisor.runtime_config = self.runtime_config
        self._subagent_supervisor.session_service = self._session_service
        self._active_task_model = task_model
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
        turn_runner, turn_cap = self._select_turn_runner()
        reset_worker_call_count()

        for model_index, task_model in enumerate(model_candidates, start=1):
            self._trace_context = replace(
                self._trace_context,
                provider=settings.model_provider,
                model=task_model,
            )
            set_trace_context(self._trace_context)
            if task_model != self._active_task_model:
                self._rebuild_agent_for_task_model(task_model)
                turn_runner = self._runner

            for attempt in range(1, self._RATE_LIMIT_MAX_RETRIES + 1):
                try:
                    # region agent log
                    emit_debug_trace(
                        run_id=self._debug_run_id(),
                        hypothesis_id="H3",
                        location="orchestrator.py:1052",
                        message="agent_attempt_started",
                        data={
                            "model": task_model,
                            "model_index": model_index,
                            "attempt": attempt,
                            "turn_cap": turn_cap,
                            "planner_mode": "planner_v2",
                        },
                    )
                    # endregion agent log
                    return await run_agent_turn(
                        runner=turn_runner,
                        session_service=self._session_service,
                        session_id=self._adk_session_id,
                        user_id=self._user_id,
                        message=message,
                        runtime_config=self.runtime_config,
                        event_callback=self._on_agent_event,
                        max_turns=turn_cap,
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
                            quota_content = (
                                f"Task model {task_model} hit quota limits. "
                                f"Switching to fallback model {next_model}."
                            )
                            await self._send_json({
                                "type": "agent_model_fallback",
                                "from_model": task_model,
                                "to_model": next_model,
                                "provider": settings.model_provider,
                                "reason": self._clip_text(str(exc), 500),
                                "attempt": attempt,
                                "step_id": new_step_id("fallback"),
                            })
                            await self._send_json({
                                "type": "agent_thinking",
                                "content": quota_content,
                            })
                            await self._persist_message(
                                role="thinking",
                                source=getattr(self, "_active_agent", "nexus_orchestrator"),
                                text=quota_content,
                            )
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
                    rate_content = (
                        f"Temporarily rate-limited by {self._rate_limit_source_label()} "
                        f"on {task_model} — backing off {wait:.0f}s "
                        f"(attempt {attempt}/{self._RATE_LIMIT_MAX_RETRIES})..."
                    )
                    await self._send_json({
                        "type": "agent_retry",
                        "provider": settings.model_provider,
                        "model": task_model,
                        "attempt": attempt,
                        "max_attempts": self._RATE_LIMIT_MAX_RETRIES,
                        "delay_ms": int(wait * 1000),
                        "reason": self._clip_text(str(exc), 500),
                        "step_id": new_step_id("retry"),
                    })
                    await self._send_json({
                        "type": "agent_thinking",
                        "content": rate_content,
                    })
                    await self._persist_message(
                        role="thinking",
                        source=getattr(self, "_active_agent", "nexus_orchestrator"),
                        text=rate_content,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            "Rate limit exceeded after retries across task models "
            f"{', '.join(model_candidates)}: {last_exc}"
        )

    def _format_uploaded_files_context(self, uploaded_files: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for raw in uploaded_files[:8]:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or raw.get("title") or raw.get("path") or "uploaded file").strip()
            path = str(raw.get("path") or "").strip()
            mime_type = str(raw.get("mime_type") or raw.get("content_type") or "").strip()
            drive_link = str(raw.get("drive_web_view_link") or "").strip()
            detail_parts = [part for part in [f"path={path}" if path else "", f"type={mime_type}" if mime_type else ""] if part]
            line = f"- {name}"
            if detail_parts:
                line += f" ({', '.join(detail_parts)})"
            if drive_link:
                line += f" drive={drive_link}"
            if mime_type == "application/pdf" or name.lower().endswith(".pdf") or path.lower().endswith(".pdf"):
                line += " [PDF: use extract_pdf_text(path=...) before reading; do not cat/base64 dump it]"
            lines.append(line)
        return "\n".join(lines)

    def _format_turn_context(
        self,
        connector_ids: list[str] | None,
        uploaded_files: list[dict[str, Any]] | None,
        tool_ids: list[str] | None = None,
    ) -> str:
        sections: list[str] = []
        # Runtime grounding: always tell the model the current date/time so it
        # never guesses "today" (which caused wrong date-range reasoning). Kept
        # in the per-turn user context (not the cached system prompt) so the
        # volatile timestamp does not break KV-cache reuse of the prefix.
        now = datetime.now(timezone.utc)
        sections.append(
            "[RUNTIME CONTEXT]\n"
            f"Current date/time (UTC): {now.strftime('%Y-%m-%d %H:%M')} "
            f"({now.strftime('%A, %d %B %Y')})"
        )
        normalized_connectors = [
            str(item).strip()
            for item in (connector_ids or [])
            if str(item).strip()
        ]
        normalized_tools = [
            str(item).strip()
            for item in (tool_ids or [])
            if str(item).strip()
        ]
        if normalized_connectors or normalized_tools:
            lines = [
                "[USER-SELECTED TOOLS — HARD RESTRICTION]",
                "Only the tools listed below are available this turn.",
                "Do NOT call any other tool; it will be blocked with TOOL_NOT_SELECTED.",
            ]
            if normalized_tools:
                lines.append(f"Built-in capabilities: {', '.join(normalized_tools[:12])}")
            if normalized_connectors:
                lines.append(f"Connectors: {', '.join(normalized_connectors[:12])}")
            sections.append("\n".join(lines))
        uploaded_block = self._format_uploaded_files_context(uploaded_files or [])
        if uploaded_block:
            sections.append(
                "[UPLOADED FILES]\n"
                f"{uploaded_block}\n"
                "Use these workspace paths directly when relevant."
            )
        return "\n\n".join(section for section in sections if section.strip())

    async def _build_turn_input(
        self,
        text: str,
        connector_ids: list[str] | None = None,
        tool_ids: list[str] | None = None,
        uploaded_files: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build the next turn input with compact resume context injected once."""
        self._last_user_message = text.strip()
        builder = TurnContextBuilder()

        if self._seed_context:
            builder.add("seed_context", self._seed_context, priority=PRIORITY_RESUME)

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
                builder.add("resume_packet", serialized, priority=PRIORITY_RESUME)
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
            builder.add("resume_fallback", self._prior_context_fallback, priority=PRIORITY_RESUME)
            self._prior_context_fallback = None
            self._seed_context = ""
        elif self._seed_context:
            self._seed_context = ""

        turn_context = self._format_turn_context(
            connector_ids, uploaded_files, tool_ids=tool_ids
        )
        if turn_context:
            builder.add("turn_context", turn_context, priority=PRIORITY_TURN)

        memory_block = await self._load_memory_block()
        if memory_block:
            builder.add("user_memory", memory_block, priority=PRIORITY_MEMORY)

        return builder.build(text).text

    async def _load_memory_block(self) -> str:
        """Fetch recent user memory facts as a context block. Best-effort."""
        if not settings.memory_enabled or not self.session.owner_id:
            return ""
        try:
            from nexus.memory import format_memory_block, get_memory_store

            facts = await get_memory_store().list_facts(
                owner_id=self.session.owner_id,
                limit=settings.memory_max_facts,
            )
            return format_memory_block(facts)
        except Exception:
            logger.debug(
                "Skipping memory injection for session %s", self.session.id, exc_info=True
            )
            return ""

    @staticmethod
    def _format_history_context(messages: list[dict]) -> str:
        """Fallback formatter when no cached context packet exists."""
        recent = messages[-15:]
        lines = []
        for msg in recent:
            role = (msg.get("role") or "user").upper()
            text = str(msg.get("text") or "").strip()
            if text:
                lines.append(f"{role}: {text[:1200]}")
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
        for message in messages[-15:]:
            role = "User" if message.get("role") == "user" else "Agent"
            text = self._clip_text(message.get("text"), 1200)
            if text:
                recent_turns.append(f"{role}: {text}")

        summary = ""
        for message in reversed(messages):
            text = self._clip_text(message.get("text"), 1500)
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

    @staticmethod
    def _should_load_cached_context(resume_mode: str) -> bool:
        """Return whether this session was explicitly created as a continuation."""
        return str(resume_mode or "").strip().lower() in _RESUME_CONTEXT_MODES

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
                    lines.extend(f"- {item}" for item in compact)
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
            "reasoning_model": self.runtime_config.qwen_planner_model or settings.planner_model,
            "vision_model": self.runtime_config.qwen_vision_model or settings.qwen_vision_model,
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
            set_owner_id(self.session.owner_id)
            set_history_repository(self.history_repository)
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

    async def _ensure_sandbox_ready(self, reason: str) -> bool:
        """Create/resume sandbox only when a user action actually needs it."""
        sandbox = getattr(self.session, "sandbox", None)
        stream_url = getattr(self.session, "stream_url", None)

        def trace_sandbox(outcome: str, error_type: str = "") -> None:
            current_sandbox = getattr(self.session, "sandbox", None)
            # region agent log
            emit_debug_trace(
                run_id=self._debug_run_id(),
                hypothesis_id="H2",
                location="orchestrator.py:1510",
                message="sandbox_readiness",
                data={
                    "reason": reason,
                    "outcome": outcome,
                    "error_type": error_type,
                    "sandbox_present": current_sandbox is not None,
                    "sandbox_alive": bool(getattr(current_sandbox, "is_alive", False)),
                    "stream_url_present": bool(getattr(self.session, "stream_url", None)),
                    "activation_callback_bound": self._ensure_sandbox_ready_callback is not None,
                },
            )
            # endregion agent log

        if sandbox is None:
            logger.warning("No sandbox attached for session %s while preparing %s", self.session.id, reason)
            trace_sandbox("missing_sandbox")
            return False
        if sandbox.is_alive and stream_url:
            if not getattr(self, "_sandbox_ready_reported", False):
                await self._send_json({"type": "sandbox_status", "status": "ready"})
                await self._send_json({"type": "vnc_url", "url": stream_url})
                self._sandbox_ready_reported = True
            trace_sandbox("already_ready")
            return True

        await self._send_json({"type": "sandbox_status", "status": "connecting", "reason": reason})
        try:
            ensure_callback = getattr(self, "_ensure_sandbox_ready_callback", None)
            if ensure_callback:
                await ensure_callback()
            elif not await self._reconnect_sandbox():
                return False

            set_sandbox(self.session.sandbox)
            set_owner_id(getattr(self.session, "owner_id", ""))
            set_history_repository(getattr(self, "history_repository", None))
            set_production_task_repository(getattr(self, "production_task_repository", None))
            set_task_id(getattr(self, "_durable_task_id", None))
            self._bind_workspace_context()
            workspace_root_ready = await self._ensure_session_workspace_root()
            if not workspace_root_ready:
                logger.warning(
                    "Sandbox became ready for session %s without a prepared workspace root",
                    self.session.id,
                )
            await self._send_json({"type": "sandbox_status", "status": "ready"})
            if getattr(self.session, "stream_url", None):
                await self._send_json({"type": "vnc_url", "url": self.session.stream_url})
            self._sandbox_ready_reported = True
            trace_sandbox("activated")
            return True
        except Exception as exc:
            trace_sandbox("activation_failed", type(exc).__name__)
            logger.exception("Sandbox activation failed for session %s", self.session.id)
            await self._send_json({
                "type": "error",
                "code": "SANDBOX_INIT_ERROR",
                "message": str(exc),
            })
            await self._send_json({
                "type": "sandbox_status",
                "status": "error",
                "message": str(exc),
            })
            return False

    async def _run_agent_tracked(
        self,
        message: str,
        *,
        source: str,
        completion_request: str | None = None,
        connector_ids: list[str] | None = None,
        tool_ids: list[str] | None = None,
    ) -> None:
        """Wrap _run_agent in a cancellable task and await it."""
        if not self._ws_connected:
            logger.info("Skipping agent turn start for session %s because the WebSocket is disconnected", self.session.id)
            return
        self._stop_requested = False
        self._turn_screenshot_count = 0
        self._turn_tool_summaries = []
        self._tool_trace_steps = {}
        resume_checkpoint = dict(getattr(self, "_resume_checkpoint", {}) or {})
        self._action_ledger = ActionLedger.from_dict(
            resume_checkpoint.get("action_ledger")
            if isinstance(resume_checkpoint.get("action_ledger"), dict)
            else None
        )
        self._resume_checkpoint = {}
        self.last_turn_result = None
        self._current_thinking = ""
        self._reasoning_status_emitted = False
        self._pending_tool_calls.clear()
        self._budget_stop_requested = False
        self._budget_stop_reason = ""
        if self._trace_context.run_id != (self._current_run_id or ""):
            self._trace_context = TraceContext(
                trace_id=new_trace_id(self._current_run_id or ""),
                run_id=self._current_run_id or "",
                provider=settings.model_provider,
                model=settings.planner_model,
            )
        set_trace_context(self._trace_context)
        # Bind run/workspace context only — do NOT boot the sandbox or create
        # a workspace here. Pure Q&A / HTML / search turns must stay sandbox-free.
        # Sandbox-backed tools call ensure_sandbox() lazily; prepare_task_workspace
        # is invoked by the planner when it actually needs a workspace.
        # See docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md.
        self._bind_workspace_context()
        from nexus.tool_catalog import resolve_tool_allowlist
        from nexus.tools._context import clear_tool_allowlist, set_tool_allowlist

        allowlist = resolve_tool_allowlist(
            tool_ids,
            connector_ids,
            mcp_tools=getattr(self, "_integration_tools", None) or None,
        )
        set_tool_allowlist(allowlist)
        try:
            # region agent log
            emit_debug_trace(
                run_id=self._debug_run_id(),
                hypothesis_id="H1,H3,H5",
                location="orchestrator.py:1602",
                message="agent_turn_started",
                data={
                    "source": source,
                    "input_chars": len(message),
                    "websocket_connected": self._ws_connected,
                    "durable_run_bound": bool(self._durable_task_id),
                    "sandbox_alive": bool(getattr(self.session.sandbox, "is_alive", False)),
                    "planner_mode": "planner_v2",
                },
            )
            # endregion agent log
            # Persist ONLY the original user request in the user-visible step. The
            # composed `message` also carries the resume checkpoint, connector
            # context, and internal repair directives, which must never surface in
            # the workflow panel. `completion_request` is the clean original request.
            display_request = completion_request if completion_request is not None else message
            self._current_turn_step_id = await self._create_step(
                step_type="agent_turn",
                title="Process request",
                detail=self._clip_text(display_request, 320),
                source=source,
                metadata={
                    "input": self._clip_text(display_request, 1200),
                    "source": source,
                    "trace_id": self._trace_context.trace_id,
                },
            )
            await self._set_run_status("running")
            self._agent_task = asyncio.create_task(
                self._run_agent(message, completion_request=completion_request)
            )
            result = await self._agent_task
            # Defensive: a delivered-with-caveat turn is terminal success. Map any
            # legacy "completed_with_caveat" to the canonical "completed" so it is
            # never treated as a failure or retried.
            if isinstance(result, dict) and result.get("status") == "completed_with_caveat":
                result["status"] = "completed"
            self.last_turn_result = dict(result)
            if result["status"] == "completed":
                await self._complete_step(
                    self._current_turn_step_id,
                    detail=self._clip_text(result.get("summary") or "Turn cancelled.", 1500),
                )
                await self._set_run_status("completed")
            elif result["status"] in {"partial", "blocked"}:
                durable_status = (
                    "waiting_approval"
                    if result["status"] == "blocked"
                    else "paused"
                )
                await self._fail_unfinished_tool_steps(
                    status="cancelled",
                    error=result.get("summary"),
                )
                await self._fail_step(
                    self._current_turn_step_id,
                    detail=self._clip_text(
                        result.get("summary") or "Turn paused.",
                        1500,
                    ),
                    error=result.get("summary"),
                    status="cancelled",
                )
                await self._set_run_status(durable_status)
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
            from nexus.tools._context import clear_tool_allowlist

            clear_tool_allowlist()
            self._tool_step_ids = {}
            self._tool_trace_steps = {}
            self._active_agent = "nexus_orchestrator"
            self._current_turn_step_id = None

    async def _run_agent(
        self,
        message: str,
        *,
        completion_request: str | None = None,
    ) -> dict[str, Any]:
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

        # If a sandbox is already alive, extend its lease. Do NOT require one
        # for every turn — Q&A / HTML / search / connector reads must work
        # without E2B. Tools marked needs_sandbox=True boot it lazily via
        # ensure_sandbox() (docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md).
        sandbox = getattr(self.session, "sandbox", None)
        if sandbox is not None and getattr(sandbox, "is_alive", False):
            try:
                sandbox.extend_timeout(900)
            except Exception:
                logger.debug("Could not extend sandbox timeout", exc_info=True)

        try:
            result = await self._run_agent_with_retry(message)
            for usage in result.usage_records:
                await self._persist_token_usage(usage)
            # region agent log
            emit_debug_trace(
                run_id=self._debug_run_id(),
                hypothesis_id="H3,H4",
                location="orchestrator.py:1700",
                message="agent_turn_returned",
                data={
                    "error_present": bool(result.error),
                    "error_type": type(result.error).__name__ if result.error else "",
                    "response_present": result.response is not None,
                    "response_chars": len(result.response or ""),
                    "usage_record_count": len(result.usage_records),
                    "sandbox_alive": bool(getattr(self.session.sandbox, "is_alive", False)),
                    "will_use_missing_final_summary": result.response is None and not result.error,
                },
            )
            # endregion agent log

            if self._current_thinking:
                await self._persist_message(
                    role="thinking",
                    source=getattr(self, "_active_agent", "nexus_orchestrator"),
                    text=self._current_thinking,
                )
                self._current_thinking = ""

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

            # Reconnect only if a sandbox was actually booted earlier and then
            # died/paused (it has a sandbox_id). A never-booted lazy sandbox has
            # no sandbox_id and must NOT be treated as "died" — reconnecting it
            # would boot an E2B VM (and run provisioning) for no reason.
            if self.session.sandbox_id and not self.session.sandbox.is_alive:
                logger.warning("Sandbox died during agent turn for session %s — reconnecting", self.session.id)
                await self._reconnect_sandbox()

            final_response = result.response
            completion_verification = await self._verify_turn_completion(
                request=completion_request if completion_request is not None else message,
                final_response=final_response,
            )

            # Honor a retryable MISSING_FINAL_RESPONSE: the model gathered
            # evidence but emitted no closing text. Re-invoke a bounded,
            # tools-off synthesis turn before surfacing a failure.
            synthesis_retries = 0
            while (
                not completion_verification.verified
                and completion_verification.error_code == "MISSING_FINAL_RESPONSE"
                and completion_verification.retryable
                and synthesis_retries < max(0, settings.max_final_synthesis_retries)
            ):
                synthesis_retries += 1
                logger.warning(
                    "MISSING_FINAL_RESPONSE; synthesis retry %d/%d for session %s",
                    synthesis_retries,
                    settings.max_final_synthesis_retries,
                    self.session.id,
                )
                retry_result = await self._run_agent_with_retry(_FINAL_SYNTHESIS_NUDGE)
                for usage in retry_result.usage_records:
                    await self._persist_token_usage(usage)
                if retry_result.error:
                    break
                if retry_result.response and retry_result.response.strip():
                    final_response = retry_result.response
                completion_verification = await self._verify_turn_completion(
                    request=completion_request if completion_request is not None else message,
                    final_response=final_response,
                )

            # Last resort: synthesize a grounded partial summary from observed
            # tool evidence instead of returning an empty failure to the user.
            if (
                not completion_verification.verified
                and completion_verification.error_code == "MISSING_FINAL_RESPONSE"
                and settings.synthesize_fallback_summary_from_ledger
            ):
                fallback_summary = self._build_ledger_fallback_summary()
                if fallback_summary:
                    logger.warning(
                        "Using ledger fallback summary for session %s",
                        self.session.id,
                    )
                    final_response = fallback_summary
                    completion_verification = await self._verify_turn_completion(
                        request=completion_request if completion_request is not None else message,
                        final_response=final_response,
                    )

            if not completion_verification.verified:
                soft_veto = (
                    settings.deliver_answer_on_soft_veto
                    and bool(final_response and final_response.strip())
                    and completion_verification.status != "blocked"
                )
                if soft_veto:
                    # Advisory veto with a real answer in hand: deliver the
                    # model's answer and attach the verification caveat as a
                    # note rather than discarding a correct response.
                    caveat = completion_verification.summary
                    if completion_verification.remaining_work:
                        caveat += "\nRemaining: " + "; ".join(
                            completion_verification.remaining_work[:4]
                        )
                    await self._reconcile_todos_at_turn_end(mark_complete=True)
                    await self._send_json({
                        "type": "transcript",
                        "role": "agent",
                        "text": final_response,
                    })
                    await self._persist_message(
                        role="agent",
                        source="agent",
                        text=final_response,
                    )
                    await self._send_json({
                        "type": "verification_caveat",
                        "code": completion_verification.error_code,
                        "message": completion_verification.summary,
                        "detail": caveat,
                    })
                    await self._send_json({
                        "type": "agent_complete",
                        "summary": final_response[:200],
                    })
                    await self._save_final_response(final_response)
                    await self._mark_summary(final_response)
                    # Canonical terminal success: the answer was delivered. Use
                    # status="completed" (not a bespoke string) so every layer --
                    # orchestrator entrypoint, agent_turn_runner, task_worker,
                    # production_tasks -- treats it as success and NEVER retries.
                    # The advisory caveat rides along in metadata + the emitted
                    # verification_caveat event, not as a distinct status.
                    return {
                        "status": "completed",
                        "summary": final_response,
                        "final_response": final_response,
                        "caveat": caveat,
                        "verification": completion_verification.to_dict(),
                    }
                failure_summary = completion_verification.summary
                if completion_verification.remaining_work:
                    failure_summary += "\nRemaining: " + "; ".join(
                        completion_verification.remaining_work[:4]
                    )
                await self._reconcile_todos_at_turn_end(mark_complete=False)
                await self._send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": failure_summary,
                })
                await self._persist_message(
                    role="agent",
                    source="completion_verifier",
                    text=failure_summary,
                )
                await self._mark_summary(
                    failure_summary,
                    status=completion_verification.status,
                    error_code=completion_verification.error_code,
                )
                await self._send_json({
                    "type": "error",
                    "code": completion_verification.error_code,
                    "message": completion_verification.summary,
                    "detail": failure_summary,
                })
                return {
                    "status": completion_verification.status,
                    "summary": failure_summary,
                    "final_response": final_response or "",
                    "verification": completion_verification.to_dict(),
                }

            if final_response:
                # Sync the To-dos panel with todo.md before the user sees the answer.
                await self._reconcile_todos_at_turn_end(mark_complete=True)
                # Send agent text response
                await self._send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": final_response,
                })
                await self._persist_message(role="agent", source="agent", text=final_response)
                # Feed to Gemini Live for TTS
                if self._is_voice_ready():
                    try:
                        await self.voice.send_text(final_response)
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
                    "summary": final_response[:200],
                })
                await self._save_final_response(final_response)
                await self._mark_summary(final_response)
                await self._create_artifact(
                    kind="summary",
                    title="Agent summary",
                    preview=self._clip_text(final_response, 280),
                    source_step_id=self._current_turn_step_id,
                    metadata={"source": "agent_complete", "role": "source"},
                )
                return {
                    "status": "completed",
                    "summary": final_response,
                    "final_response": final_response,
                    "verification": completion_verification.to_dict(),
                }
            await self._reconcile_todos_at_turn_end(mark_complete=False)
            return {
                "status": "failed",
                "summary": "The model ended without a final response.",
                "final_response": "",
                "verification": completion_verification.to_dict(),
            }

        except _AgentStopped:
            if self._budget_stop_requested:
                summary = self._build_budget_partial_summary()
                if self._current_thinking:
                    await self._persist_message(
                        role="thinking",
                        source=getattr(self, "_active_agent", "nexus_orchestrator"),
                        text=self._current_thinking,
                    )
                    self._current_thinking = ""
                await self._send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": summary,
                })
                await self._persist_message(role="agent", source="agent", text=summary)
                guard = get_task_budget_guard()
                verification = {
                    "verified": False,
                    "status": "partial",
                    "method": "budget",
                    "summary": self._budget_stop_reason,
                    "error_code": (
                        guard.exhausted_code
                        if guard is not None
                        else "BUDGET_EXHAUSTED"
                    ),
                    "evidence": self._turn_tool_summaries[:4],
                    "remaining_work": [
                        "Resume from the durable checkpoint with a renewed budget."
                    ],
                    "retryable": False,
                }
                await self._send_json({
                    "type": "verification_result",
                    **verification,
                    "action_count": len(self._action_ledger.records),
                })
                await self._save_final_response(summary)
                await self._mark_summary(
                    summary,
                    status="paused",
                    error_code=verification["error_code"],
                )
                await self._create_artifact(
                    kind="summary",
                    title="Budget-safe partial summary",
                    preview=self._clip_text(summary, 280),
                    source_step_id=self._current_turn_step_id,
                    metadata={"source": "budget_stop", "role": "source"},
                )
                await self._save_durable_checkpoint(
                    reason="budget_exhausted",
                    verification=verification,
                )
                return {
                    "status": "partial",
                    "summary": summary,
                    "final_response": summary,
                    "verification": verification,
                    "checkpoint": self._durable_checkpoint_payload(
                        reason="budget_exhausted",
                        verification=verification,
                    ),
                }
            logger.info("Agent stopped via _AgentStopped for session %s", self.session.id)
            raise

        except Exception as exc:
            logger.exception("Agent turn failed")
            if self._current_thinking:
                try:
                    await self._persist_message(
                        role="thinking",
                        source=getattr(self, "_active_agent", "nexus_orchestrator"),
                        text=self._current_thinking,
                    )
                except Exception:
                    pass
                self._current_thinking = ""
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

    async def _emit_reasoning(self, text: str) -> None:
        """Apply the reasoning visibility + persistence policy to one burst.

        ``settings.reasoning_visibility``:
          - "hidden":  never emit reasoning to the client.
          - "compact": emit a single lightweight status per reasoning burst
            (reset whenever a tool phase starts), never the raw tokens.
          - "full":    emit the sanitized reasoning text (legacy behavior).
        Raw reasoning is persisted only when ``settings.persist_reasoning`` is
        true, so chain-of-thought does not re-enter the model's context later.
        """
        if settings.persist_reasoning:
            self._current_thinking += text

        visibility = settings.reasoning_visibility
        if visibility == "hidden":
            return
        if visibility == "compact":
            if not self._reasoning_status_emitted:
                self._reasoning_status_emitted = True
                await self._send_json({
                    "type": "agent_thinking",
                    "content": "Thinking...",
                })
            return
        # "full" (or any unknown value): sanitized reasoning text.
        await self._send_json({"type": "agent_thinking", "content": text})

    async def _on_agent_event(self, event: Any) -> None:
        """Callback for each ADK agent event — stream to frontend."""
        if not hasattr(self, "_action_ledger"):
            self._action_ledger = ActionLedger()
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
            event_parts = getattr(getattr(event, "content", None), "parts", None) or []
            response_statuses: list[dict[str, str]] = []
            for event_part in event_parts:
                event_response = getattr(event_part, "function_response", None)
                if not event_response:
                    continue
                event_response_mapping = self._coerce_mapping(
                    self._get_attr(event_response, "response")
                )
                response_statuses.append(
                    {
                        "tool": str(self._get_attr(event_response, "name") or "unknown")[:80],
                        "status": str(event_response_mapping.get("status") or ""),
                        "error_code": str(event_response_mapping.get("error_code") or ""),
                    }
                )
            # region agent log
            emit_debug_trace(
                run_id=self._debug_run_id(),
                hypothesis_id="H3,H4",
                location="orchestrator.py:1845",
                message="agent_event_observed",
                data={
                    "author": str(author or "")[:80],
                    "function_calls": [
                        str(self._get_attr(call, "name", "tool_name") or "unknown")[:80]
                        for call in function_calls[:8]
                    ],
                    "function_response_statuses": response_statuses[:8],
                    "is_final_response": self._is_final_response(event),
                    "part_count": len(event_parts),
                },
            )
            # endregion agent log

            for fc in function_calls:
                self._raise_if_agent_should_stop()
                if self._current_thinking:
                    await self._persist_message(
                        role="thinking",
                        source=getattr(self, "_active_agent", "nexus_orchestrator"),
                        text=self._current_thinking
                    )
                    self._current_thinking = ""
                tool_name = self._get_attr(fc, "name", "tool_name") or str(fc)
                tool_args = self._get_attr(fc, "args", "tool_input") or {}
                call_id = str(self._get_attr(fc, "id", "call_id") or "")
                trace_step_id = call_id or new_step_id("tool")
                trace_started_ms = monotonic_ms()
                action_decision = ActionDecision.from_tool_call(
                    action_id=trace_step_id,
                    tool_name=str(tool_name),
                    arguments=self._redact_mapping(self._coerce_mapping(tool_args)),
                )
                self._action_ledger.start(action_decision)
                self._trace_context = replace(
                    self._trace_context,
                    step_id=trace_step_id,
                    parent_step_id=self._current_turn_step_id or "",
                )
                set_trace_context(self._trace_context)
                
                # Map specific tools to specialized step types for rich visualizers
                step_type = "tool_call"
                if tool_name == "gmail_send":
                    step_type = "gmail"
                elif tool_name == "calendar_create":
                    step_type = "calendar"
                elif tool_name == "tasks_create":
                    step_type = "tasks"

                step_title = self._tool_step_title(tool_name, tool_args)
                step_id = await self._create_step(
                    step_type=step_type,
                    title=step_title,
                    detail=self._clip_text(self._redact_mapping(self._coerce_mapping(tool_args)), 320),
                    source=getattr(self, "_active_agent", "nexus_orchestrator"),
                    metadata={
                        "tool": tool_name,
                        "args": self._redact_mapping(self._coerce_mapping(tool_args)),
                        "trace_id": self._trace_context.trace_id,
                        "trace_step_id": trace_step_id,
                        "provider": self._trace_context.provider,
                        "model": self._trace_context.model,
                        "action_decision": {
                            "expected_outcome": action_decision.expected_outcome,
                            "verification_method": action_decision.verification_method,
                            "retry_policy": {
                                "max_attempts": action_decision.retry_policy.max_attempts,
                                "backoff_seconds": action_decision.retry_policy.backoff_seconds,
                                "switch_strategy_on_repeat": action_decision.retry_policy.switch_strategy_on_repeat,
                            },
                            "completion_condition": action_decision.completion_condition,
                        },
                    },
                )
                if step_id:
                    self._tool_step_ids.setdefault(tool_name, []).append(step_id)
                self._tool_trace_steps.setdefault(tool_name, []).append({
                    "step_id": trace_step_id,
                    "workflow_step_id": step_id,
                    "started_ms": trace_started_ms,
                    "call_id": call_id,
                })
                if call_id:
                    self._pending_tool_calls[call_id] = {
                        "tool_name": tool_name,
                        "workflow_step_id": step_id,
                        "trace_step_id": trace_step_id,
                        "started_ms": trace_started_ms,
                    }
                # New tool phase -> allow one fresh compact "Thinking..." status
                # for the reasoning burst that follows this call's result.
                self._reasoning_status_emitted = False
                
                import json
                await self._persist_message(
                    role="tool_call",
                    source=getattr(self, "_active_agent", "nexus_orchestrator"),
                    text=f"Tool: {tool_name}\nArgs: {json.dumps(self._redact_mapping(self._coerce_mapping(tool_args)))}"
                )

                await self._send_json({
                    "type": "agent_tool_call",
                    "tool": tool_name,
                    "args": self._redact_mapping(self._coerce_mapping(tool_args)),
                    "step_id": trace_step_id,
                    "workflow_step_id": step_id,
                    "status": "started",
                    "provider": self._trace_context.provider,
                    "model": self._trace_context.model,
                    "expected_outcome": action_decision.expected_outcome,
                    "verification_method": action_decision.verification_method,
                    "retry_policy": {
                        "max_attempts": action_decision.retry_policy.max_attempts,
                        "backoff_seconds": action_decision.retry_policy.backoff_seconds,
                        "switch_strategy_on_repeat": action_decision.retry_policy.switch_strategy_on_repeat,
                    },
                    "completion_condition": action_decision.completion_condition,
                })

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) or []
            is_final = self._is_final_response(event)

            for part in parts:
                self._raise_if_agent_should_stop()
                text = getattr(part, "text", None)
                if text and not is_final:
                    clean = sanitize_stream_text(text)
                    if not clean:
                        continue
                    kind = classify_part(
                        part, reasoning_is_text=settings.reasoning_is_text
                    )
                    if kind == "reasoning":
                        await self._emit_reasoning(clean)
                    else:
                        # Genuine intermediate answer text (non-reasoning
                        # providers): keep prior behavior, sanitized.
                        if settings.persist_reasoning:
                            self._current_thinking += clean
                        await self._send_json({
                            "type": "agent_thinking",
                            "content": clean,
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
                    resp_id = str(self._get_attr(fn_resp, "id", "call_id") or "")
                    step_id = None
                    trace_step: dict[str, Any] = {}
                    matched = (
                        self._pending_tool_calls.pop(resp_id, None)
                        if resp_id
                        else None
                    )
                    if matched is not None:
                        # Precise: pair by function-call id. Keep the tool_name
                        # FIFO maps in sync by removing the matched entries.
                        step_id = matched.get("workflow_step_id")
                        trace_step = {
                            "step_id": matched.get("trace_step_id"),
                            "workflow_step_id": matched.get("workflow_step_id"),
                            "started_ms": matched.get("started_ms"),
                            "call_id": resp_id,
                        }
                        name_steps = self._tool_step_ids.get(tool_name)
                        if name_steps and step_id in name_steps:
                            name_steps.remove(step_id)
                            if not name_steps:
                                self._tool_step_ids.pop(tool_name, None)
                        name_traces = self._tool_trace_steps.get(tool_name)
                        if name_traces:
                            self._tool_trace_steps[tool_name] = [
                                t for t in name_traces if t.get("call_id") != resp_id
                            ]
                            if not self._tool_trace_steps[tool_name]:
                                self._tool_trace_steps.pop(tool_name, None)
                    else:
                        # Fallback: no id available -> FIFO by tool name.
                        pending_steps = self._tool_step_ids.get(tool_name, [])
                        if pending_steps:
                            step_id = pending_steps.pop(0)
                            if not pending_steps:
                                self._tool_step_ids.pop(tool_name, None)
                        pending_trace_steps = self._tool_trace_steps.get(tool_name, [])
                        if pending_trace_steps:
                            trace_step = pending_trace_steps.pop(0)
                            if not pending_trace_steps:
                                self._tool_trace_steps.pop(tool_name, None)
                    trace_step_id = str(
                        trace_step.get("step_id") or self._get_attr(fn_resp, "id") or new_step_id("tool")
                    )
                    latency_ms = max(
                        0,
                        monotonic_ms() - int(trace_step.get("started_ms") or monotonic_ms()),
                    )
                    tool_status, error_code, retry_reason = result_status(output_mapping)
                    action_observation = ActionObservation.from_tool_result(
                        action_id=trace_step_id,
                        tool_name=str(tool_name),
                        result=output_mapping,
                        fallback_summary=output_str,
                    )
                    self._action_ledger.finish(action_observation)
                    result_metadata = self._build_tool_result_metadata(
                        tool_name=tool_name,
                        output_mapping=output_mapping,
                        output_str=output_str,
                    )
                    result_metadata.update({
                        "trace_id": self._trace_context.trace_id,
                        "trace_step_id": trace_step_id,
                        "status": tool_status,
                        "error_code": error_code,
                        "retry_reason": retry_reason,
                        "latency_ms": latency_ms,
                        "provider": self._trace_context.provider,
                        "model": self._trace_context.model,
                        "action_observation": {
                            "status": action_observation.status,
                            "evidence": action_observation.evidence,
                            "artifacts": action_observation.artifacts,
                            "remaining_work": action_observation.remaining_work,
                            "retryable": action_observation.retryable,
                            "verified": action_observation.verified,
                        },
                    })

                    await self._send_json({
                        "type": "agent_tool_result",
                        "tool": tool_name,
                        "output": output_str,
                        "result_summary": safe_trace_value(output_mapping),
                        "step_id": trace_step_id,
                        "workflow_step_id": step_id,
                        "status": tool_status,
                        "error_code": error_code,
                        "retry_reason": retry_reason,
                        "latency_ms": latency_ms,
                        "evidence": action_observation.evidence,
                        "artifacts": action_observation.artifacts,
                        "remaining_work": action_observation.remaining_work,
                        "retryable": action_observation.retryable,
                        "verified": action_observation.verified,
                    })
                    if tool_status in {"error", "failed", "cancelled", "denied"}:
                        await self._fail_step(
                            step_id,
                            detail=self._clip_text(output_str or retry_reason, 1500),
                            error=self._clip_text(retry_reason or output_str or error_code, 500),
                            metadata=result_metadata,
                            status="cancelled" if tool_status in {"cancelled", "denied"} else "failed",
                        )
                    else:
                        await self._complete_step(
                            step_id,
                            detail=self._clip_text(output_str, 1500),
                            metadata=result_metadata,
                        )
                    self._trace_context = replace(self._trace_context, step_id="")
                    set_trace_context(self._trace_context)

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
                    
                    await self._persist_message(
                        role="tool_result",
                        source=tool_name,
                        text=output_str
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
                    await self._save_durable_checkpoint(
                        reason=f"tool_result:{tool_name}",
                        last_step_id=trace_step_id,
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

    def _redact_mapping(self, value: dict[str, Any]) -> dict[str, Any]:
        redacted = redact_sensitive(value)
        return redacted if isinstance(redacted, dict) else {"value": redacted}

    def mark_ws_disconnected(self) -> None:
        self._ws_connected = False
        self._stop_requested = True

    def _raise_if_agent_should_stop(self) -> None:
        if self._stop_requested:
            raise _AgentStopped()
        guard = get_task_budget_guard()
        if guard is not None and guard.exhausted:
            self._budget_stop_requested = True
            self._budget_stop_reason = guard.exhausted_reason
            raise _AgentStopped()
        if self._ws_is_open():
            return
        if self._ws_connected:
            logger.info("WebSocket disconnected — stopping agent turn early")
        self.mark_ws_disconnected()
        raise _AgentStopped()

    def _build_ledger_fallback_summary(self) -> str:
        """Synthesize a partial summary from observed tool evidence.

        Used as a last resort when the model produced no closing text so the
        user receives a grounded summary instead of an empty failure.
        """
        findings = list(self._turn_tool_summaries[:6])
        if not findings:
            for record in self._action_ledger.records:
                observation = record.observation
                if observation is not None and observation.evidence:
                    findings.append(
                        f"{observation.tool}: "
                        f"{self._clip_text(observation.evidence[0], 200)}"
                    )
                if len(findings) >= 6:
                    break
        if not findings:
            return ""
        lines = ["Here is a summary based on the information gathered:"]
        lines.extend(f"- {item}" for item in findings)
        return "\n".join(lines)

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

    async def _verify_turn_completion(
        self,
        *,
        request: str,
        final_response: str | None,
    ):
        """Persist and emit deterministic completion-verification evidence."""
        verification = verify_completion(
            request=request,
            final_response=final_response,
            ledger=self._action_ledger,
        )
        active_subagents = [
            record
            for record in self._subagent_supervisor.list()
            if record.status in {"queued", "running"}
            or (
                record.status == "completed"
                and not record.result_consumed
            )
        ]
        if active_subagents:
            verification = CompletionVerification(
                verified=False,
                status="partial",
                method="subagent_lifecycle",
                summary=(
                    "Background work is still running or has uncollected "
                    "results; it must be consumed before this turn can complete."
                ),
                error_code="SUBAGENTS_PENDING",
                evidence=[
                    f"{record.subagent_id}:{record.status}"
                    for record in active_subagents[:12]
                ],
                remaining_work=[
                    "Await the durable subagents and consume their results "
                    "before final synthesis."
                ],
                retryable=True,
            )
        payload = {
            "type": "verification_result",
            **verification.to_dict(),
            "action_count": len(self._action_ledger.records),
        }
        await self._send_json(payload)
        step_id = await self._create_step(
            step_type="verification",
            title="Verify requested outcome",
            detail=self._clip_text(verification.summary, 1500),
            source="completion_verifier",
            metadata={
                "verification": verification.to_dict(),
                "action_ledger": self._action_ledger.to_dict(),
            },
        )
        if verification.verified:
            await self._complete_step(
                step_id,
                detail=verification.summary,
                metadata={
                    "verification": verification.to_dict(),
                    "action_ledger": self._action_ledger.to_dict(),
                },
            )
        else:
            await self._fail_step(
                step_id,
                detail=verification.summary,
                error=verification.error_code,
                metadata={
                    "verification": verification.to_dict(),
                    "action_ledger": self._action_ledger.to_dict(),
                },
                status=(
                    "cancelled"
                    if verification.status == "blocked"
                    else "failed"
                ),
            )
        await self._save_durable_checkpoint(
            reason="completion_verification",
            last_step_id=step_id or "",
            verification=verification.to_dict(),
        )
        return verification

    def _durable_checkpoint_payload(
        self,
        *,
        reason: str,
        last_step_id: str = "",
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        guard = get_task_budget_guard()
        return {
            "version": 1,
            "reason": reason,
            "trace_id": self._trace_context.trace_id,
            "run_id": self._current_run_id or "",
            "last_step_id": last_step_id,
            "action_ledger": self._action_ledger.to_dict(),
            "subagents": self._subagent_supervisor.checkpoint_snapshot(),
            "budget": guard.checkpoint() if guard is not None else {},
            "verification": verification or {},
        }

    async def _save_durable_checkpoint(
        self,
        *,
        reason: str,
        last_step_id: str = "",
        verification: dict[str, Any] | None = None,
    ) -> None:
        if (
            self.production_task_repository is None
            or not self._durable_task_id
            or not self._durable_run_id
        ):
            return
        try:
            await self.production_task_repository.save_checkpoint(
                task_id=self._durable_task_id,
                run_id=self._durable_run_id,
                owner_id=self.session.owner_id,
                checkpoint=self._durable_checkpoint_payload(
                    reason=reason,
                    last_step_id=last_step_id,
                    verification=verification,
                ),
            )
        except Exception:
            logger.warning(
                "Failed to persist durable checkpoint for %s/%s",
                self._durable_task_id,
                self._durable_run_id,
                exc_info=True,
            )

    def _build_missing_final_response_summary(self, message: str) -> str:
        findings = self._turn_tool_summaries[:6]
        lines = [
            "Tool work completed, but the model did not produce a final answer.",
        ]
        task = self._clip_text(message or self._last_user_message, 240)
        if task:
            lines.append(f"Task: {task}")
        if findings:
            lines.append("Findings so far:")
            lines.extend(f"- {item}" for item in findings)
            lines.append("Ask me to continue if you want a deeper synthesis.")
        else:
            lines.append("No usable tool summary was returned, so I cannot safely claim a result.")
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
        turn_summary = self._clip_text(
            str(
                output_mapping.get("summary")
                or output_mapping.get("description")
                or output_mapping.get("error")
                or output_str
            ),
            180,
        )
        if turn_summary:
            self._turn_tool_summaries.append(f"{tool_name}: {turn_summary}")
            self._turn_tool_summaries = self._turn_tool_summaries[-6:]

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
        history_repository = getattr(self, "history_repository", None)
        if not history_repository or not text.strip():
            return
        try:
            await history_repository.append_message(
                session_id=self.session.id,
                owner_id=getattr(self.session, "owner_id", ""),
                role=role,
                source=source,
                text=text.strip(),
            )
        except Exception:
            logger.exception("Failed to persist %s message for session %s", role, self.session.id)

    async def _persist_token_usage(self, usage: TokenUsageRecord) -> None:
        budget_guard = get_task_budget_guard()
        estimated_credits = calculate_usage_credits(
            source=usage.source,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        if budget_guard is not None:
            budget_guard.consume_credits(estimated_credits)
        if not self.history_repository:
            return
        try:
            credits_charged, session_totals = await self.history_repository.append_token_usage(
                session_id=self.session.id,
                owner_id=self.session.owner_id,
                source=usage.source,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
            await self._send_json({
                "type": "token_usage",
                "model": usage.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "max_tokens": int(settings.model_context_limit),
                "session_input_tokens": int(session_totals.get("input", 0) or 0),
                "session_output_tokens": int(session_totals.get("output", 0) or 0),
                "session_total_tokens": int(session_totals.get("total", 0) or 0),
            })
            # Tokens remain internal telemetry; credits are the user-facing allowance.
            if usage.total_tokens > 0:
                await self.history_repository.increment_user_token_usage(
                    self.session.owner_id,
                    usage.total_tokens,
                )
            if credits_charged > 0:
                if budget_guard is not None and credits_charged > estimated_credits:
                    budget_guard.consume_credits(
                        credits_charged - estimated_credits
                    )
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
        credits = calculate_screenshot_credits(analysis_mode)
        if credits <= 0:
            return
        budget_guard = get_task_budget_guard()
        if budget_guard is not None:
            budget_guard.consume_credits(credits)
        if not self.history_repository:
            return
        try:
            await self.history_repository.record_credit_charge(
                session_id=self.session.id,
                owner_id=self.session.owner_id,
                source="vision.qwen_screenshot",
                model=self.runtime_config.qwen_vision_model or settings.qwen_vision_model,
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
        if hasattr(self.session, "sandbox") and not await self._ensure_sandbox_ready("workspace_prep"):
            logger.warning("Sandbox not available for workspace preparation in session %s", self.session.id)
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
            result_detail = result.get("detail") if isinstance(result.get("detail"), dict) else result
            result_metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
            if result.get("status") == "error" or result.get("error"):
                raise RuntimeError(str(result.get("summary") or result.get("error")))
            workspace_path = (
                result_detail.get("workspace_path")
                or result_metadata.get("workspace_path")
                or self._workspace_path
                or derive_session_workspace_path(self.session.id)
            )
            touched_files = result_detail.get("touched_files") or result_metadata.get("touched_files") or []
            created = bool(result_detail.get("created", result_metadata.get("created", False)))
            detail = (
                f"Created workspace at {workspace_path}."
                if created
                else f"Workspace ready at {workspace_path}."
            )
            if touched_files:
                detail += f" Updated: {', '.join(str(name) for name in touched_files)}."
            await self._complete_step(
                step_id,
                detail=detail,
                metadata={
                    "workspace_path": workspace_path,
                    "touched_files": touched_files,
                    "created": created,
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

    async def _reconcile_todos_at_turn_end(self, *, mark_complete: bool) -> None:
        """Push the latest todo.md state to the UI at turn end.

        On verified success, remaining pending/in_progress items are marked done
        so the To-dos panel matches what the agent actually finished.
        """
        try:
            self._bind_workspace_context()
            await reconcile_todo_list_at_turn_end(mark_complete=mark_complete)
        except Exception:
            logger.debug(
                "Todo reconciliation skipped for session %s",
                self.session.id,
                exc_info=True,
            )

    async def _save_final_response(self, text: str) -> None:
        if not text.strip() or not self._current_run_id:
            return
        try:
            self._bind_workspace_context()
            result = await write_workspace_file("outputs/final.md", text, append=False)
            output_path = result.get("output_path")
            if isinstance(output_path, str) and output_path:
                is_url = output_path.startswith(("http:", "https:", "data:"))
                await self._create_artifact(
                    kind="workspace_output",
                    title="final.md",
                    preview=self._clip_text(text, 280),
                    source_step_id=self._current_turn_step_id,
                    path=result.get("relative_path") or "outputs/final.md",
                    url=output_path if is_url else None,
                    metadata={
                        "workspace_path": self._workspace_path or "",
                        "workspace_relative_path": result.get("relative_path") or "outputs/final.md",
                        "source": "final_response",
                        "role": "source",
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
            await self._ensure_history_run(
                self._current_run_id,
                task_id=getattr(self.session, "task_id", None),
            )
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
            correlated_metadata = dict(metadata or {})
            trace_context = getattr(self, "_trace_context", None)
            if trace_context is not None:
                correlated_metadata.setdefault("trace_id", trace_context.trace_id)
                correlated_metadata.setdefault("provider", trace_context.provider)
                correlated_metadata.setdefault("model", trace_context.model)
            await self._ensure_history_run(
                self._current_run_id,
                task_id=getattr(self.session, "task_id", None),
            )
            step = await self.history_repository.create_step(
                session_id=self.session.id,
                run_id=self._current_run_id,
                step_type=step_type,
                title=title,
                detail=detail,
                source=source,
                external_ref=external_ref,
                metadata=correlated_metadata,
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

    # Working files / evidence — shown in Sources panel, never as chat cards.
    _SOURCE_ARTIFACT_KINDS = frozenset({
        "summary",
        "screenshot_reference",
        "export_reference",
        "workspace_output",
    })

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
        
        # Fail-safe: if path is a URL or data URI, move it to url
        if path and path.startswith(("http:", "https:", "data:")):
            if not url:
                url = path
            path = None

        # Normalize SaaS-style role: deliverables (PDF/DOCX/HTML/images) vs
        # sources (search dumps, scrapes, screenshots, agent summaries).
        normalized_meta: dict[str, Any] = dict(metadata or {})
        role = normalized_meta.get("role")
        if role not in ("deliverable", "source"):
            if kind in self._SOURCE_ARTIFACT_KINDS:
                normalized_meta["role"] = "source"
            elif isinstance(path, str) and path.replace("\\", "/").startswith("sources/"):
                normalized_meta["role"] = "source"
            else:
                normalized_meta["role"] = "deliverable"

        try:
            await self._ensure_history_run(
                self._current_run_id,
                task_id=getattr(self.session, "task_id", None),
            )
            artifact = await self.history_repository.create_artifact(
                session_id=self.session.id,
                run_id=self._current_run_id,
                kind=kind,
                title=title,
                preview=preview,
                source_step_id=source_step_id,
                path=path,
                url=url,
                metadata=normalized_meta,
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

    # Document tools that create, upload, AND emit their own durable artifact
    # via the artifact callback. Excluded from reference-artifact minting so one
    # generated file yields exactly one artifact id.
    _SELF_PERSISTING_ARTIFACT_TOOLS = frozenset({
        "publish_html_artifact",
        "generate_pdf_report",
        "generate_excel_report",
        "generate_docx_report",
        "save_as_artifact",
    })

    def _extract_reference_artifact(
        self,
        tool_name: str,
        output_mapping: dict[str, Any],
        output_str: str,
    ) -> dict[str, Any] | None:
        # Tools that create AND emit their own durable artifact (with GCS
        # bucket/blob metadata) must NOT get a second "reference" artifact minted
        # here -- that produced duplicate ids and a metadata-poor copy that the
        # UI showed instead of the durable one.
        if tool_name in self._SELF_PERSISTING_ARTIFACT_TOOLS:
            return None
        # Defense in depth: if any tool result already reports an artifact_id, it
        # has already persisted+emitted its artifact; do not duplicate it.
        for container in (output_mapping, output_mapping.get("detail"), output_mapping.get("metadata")):
            if isinstance(container, dict) and str(container.get("artifact_id") or "").strip():
                return None
        if tool_name == "take_screenshot":
            description = output_mapping.get("description") if isinstance(output_mapping.get("description"), str) else output_str
            return {
                "kind": "screenshot_reference",
                "title": "Screenshot capture",
                "preview": self._clip_text(description, 280),
                "metadata": {"tool": tool_name, "role": "source"},
            }

        for key in ("path", "file_path", "output_path", "saved_path", "url", "download_url"):
            value = output_mapping.get(key)
            if isinstance(value, str) and value.strip():
                is_url_val = value.startswith(("http:", "https:", "data:"))
                
                # Extract relative path from output_mapping if possible
                rel_path = output_mapping.get("relative_path")
                if not isinstance(rel_path, str) or not rel_path.strip():
                    rel_path = value if not is_url_val else None

                return {
                    "kind": "export_reference",
                    "title": tool_name.replace("_", " "),
                    "preview": self._clip_text(output_str or value, 280),
                    "path": rel_path,
                    "url": value if is_url_val else None,
                    "metadata": {"tool": tool_name, "ref_key": key, "role": "source"},
                }
        for container_key in ("detail", "metadata"):
            nested = output_mapping.get(container_key)
            if not isinstance(nested, dict):
                continue
            for key in ("path", "file_path", "output_path", "saved_path", "url", "download_url"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    is_url_val = value.startswith(("http:", "https:", "data:"))
                    
                    # Try to get relative path from nested or output_mapping
                    rel_path = nested.get("relative_path") or output_mapping.get("relative_path")
                    if not isinstance(rel_path, str) or not rel_path.strip():
                        rel_path = value if not is_url_val else None

                    return {
                        "kind": "export_reference",
                        "title": tool_name.replace("_", " "),
                        "preview": self._clip_text(output_str or value, 280),
                        "path": rel_path,
                        "url": value if is_url_val else None,
                        "metadata": {
                            "tool": tool_name,
                            "ref_key": key,
                            "ref_container": container_key,
                            "role": "source",
                        },
                    }
        return None

    @staticmethod
    def _tool_step_title(tool_name: str, tool_args: Any) -> str:
        args = tool_args if isinstance(tool_args, dict) else {}
        if tool_name == "publish_html_artifact":
            title = args.get("title")
            if isinstance(title, str) and title.strip():
                return f"HTML artifact: {title.strip()[:120]}"
            return "HTML artifact"
        if tool_name == "render_ui":
            title = args.get("title")
            component_type = args.get("component_type")
            if isinstance(title, str) and title.strip():
                prefix = f"{component_type} " if isinstance(component_type, str) and component_type.strip() else ""
                return f"C1 {prefix}visual: {title.strip()[:120]}"
            return "C1 visual"
        return f"Tool: {tool_name}"

    def _build_tool_result_metadata(
        self,
        *,
        tool_name: str,
        output_mapping: dict[str, Any],
        output_str: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "tool": tool_name,
            "output": self._clip_metadata_text(output_str, 8000),
        }
        clipped_result = self._clip_metadata_value(self._redact_mapping(output_mapping))
        if isinstance(clipped_result, dict):
            metadata["result"] = clipped_result

        sources: list[dict[str, Any]] = [output_mapping]
        detail = output_mapping.get("detail")
        if isinstance(detail, dict):
            sources.append(detail)

        for key in (
            "command",
            "stdout_excerpt",
            "stderr_excerpt",
            "exit_code",
            "query",
            "results",
            "saved_path",
            "url",
            "title",
            "artifact_id",
            "filename",
            "workspace_file",
            "relative_path",
            "content",
            "bytes_written",
            "append",
            "output_path",
            "component_type",
        ):
            for source in sources:
                if key in source and key not in metadata:
                    metadata[key] = self._clip_metadata_value(source[key])
        return metadata

    def _clip_metadata_value(self, value: Any, *, text_limit: int = 12000) -> Any:
        if isinstance(value, str):
            return self._clip_metadata_text(value, text_limit)
        if isinstance(value, list):
            return [self._clip_metadata_value(item, text_limit=text_limit) for item in value[:20]]
        if isinstance(value, dict):
            return {
                str(key): self._clip_metadata_value(raw, text_limit=text_limit)
                for key, raw in list(value.items())[:40]
            }
        return value

    @staticmethod
    def _clip_metadata_text(value: str, limit: int) -> str:
        text = value or ""
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"
