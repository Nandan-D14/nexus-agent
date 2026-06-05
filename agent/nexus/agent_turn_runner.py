# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared agent-turn runner for live and durable execution adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocketState

from nexus.orchestrator import NexusOrchestrator
from nexus.production_tasks import map_history_status_to_durable
from nexus.runtime_config import resolve_session_runtime_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentTurnRequest:
    task_id: str
    run_id: str
    owner_id: str
    session_id: str
    title: str
    input_text: str
    connector_ids: list[str] = field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = field(default_factory=list)
    emit_user_transcript: bool = True


@dataclass(frozen=True)
class AgentTurnOutcome:
    status: str
    summary: str


class AgentTurnRunner:
    """Runs one agent turn using the existing orchestrator behavior."""

    def __init__(self, *, session_manager, production_task_repository) -> None:
        self.session_manager = session_manager
        self.production_task_repository = production_task_repository

    async def run(self, request: AgentTurnRequest) -> AgentTurnOutcome:
        history_repository = self.session_manager.history_repository
        user_settings = {}
        if history_repository:
            try:
                user_settings = await history_repository.get_user_settings(request.owner_id)
            except Exception:
                logger.warning("Failed to load user settings for durable task %s", request.task_id, exc_info=True)
        runtime_config = resolve_session_runtime_config(user_settings)

        session = await self.session_manager.get_session(request.session_id)
        if not session or session.owner_id != request.owner_id or getattr(session, "runtime_config", None) is None:
            session = await self.session_manager.create_session(
                owner_id=request.owner_id,
                runtime_config=runtime_config,
                session_id=request.session_id,
                task_id=request.task_id,
                initial_title=request.title,
            )

        session.task_id = request.task_id
        session.current_run_id = request.run_id
        session.run_status = "queued"

        async def activate_sandbox() -> None:
            await self.session_manager.activate_session(session.id)

        orchestrator = NexusOrchestrator(
            session=session,
            ws=WorkerEventWebSocket(),
            history_repository=history_repository,
            production_task_repository=self.production_task_repository,
            ensure_sandbox_ready=activate_sandbox,
        )
        try:
            await orchestrator.initialize(lazy_sandbox=True)
            await orchestrator.handle_text_input(
                request.input_text,
                connector_ids=request.connector_ids,
                uploaded_files=request.uploaded_files,
                emit_user_transcript=request.emit_user_transcript,
            )
            durable_status = map_history_status_to_durable(session.run_status)
            if durable_status in {"failed", "cancelled"}:
                return AgentTurnOutcome(durable_status, f"Agent turn {durable_status}.")
            return AgentTurnOutcome("completed", "Agent turn completed.")
        finally:
            await orchestrator.close()


class WorkerEventWebSocket:
    """No-op WebSocket facade used by durable workers."""

    client_state = WebSocketState.CONNECTED
    application_state = WebSocketState.CONNECTED

    async def send_json(self, data: dict) -> None:
        return None

    async def send_bytes(self, data: bytes) -> None:
        return None
