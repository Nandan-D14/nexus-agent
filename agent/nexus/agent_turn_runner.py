# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared agent-turn runner for live and durable execution adapters."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import Any

from starlette.websockets import WebSocketState

from nexus.orchestrator import NexusOrchestrator
from nexus.production_tasks import map_history_status_to_durable
from nexus.runtime_config import resolve_session_runtime_config
from nexus.task_budget import TaskBudgetGuard
from nexus.tools._context import (
    clear_unattended_tools,
    set_task_budget_guard,
    set_unattended_tools,
)

logger = logging.getLogger(__name__)

_CANCEL_POLL_SECONDS = 5.0


@dataclass(frozen=True)
class AgentTurnRequest:
    task_id: str
    run_id: str
    owner_id: str
    session_id: str
    title: str
    input_text: str
    connector_ids: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = field(default_factory=list)
    emit_user_transcript: bool = True
    autonomy_mode: str = "manual"
    budget: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    allowed_unattended_tools: list[str] = field(default_factory=list)
    skip_confirmations: bool = False


@dataclass(frozen=True)
class AgentTurnOutcome:
    status: str
    summary: str
    final_response: str = ""
    verification: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False


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
        skip_confirm = bool(getattr(request, "skip_confirmations", False))
        from nexus.tools._context import set_skip_confirmations

        set_skip_confirmations(skip_confirm)

        runtime_config = resolve_session_runtime_config(user_settings)
        runtime_config = replace(
            runtime_config,
            autonomy_mode="auto" if skip_confirm else request.autonomy_mode,
        )
        prior_budget = (
            request.checkpoint.get("budget")
            if isinstance(request.checkpoint.get("budget"), dict)
            else {}
        )
        budget_guard = TaskBudgetGuard.from_budget(
            request.budget,
            checkpoint=prior_budget,
        )
        set_task_budget_guard(budget_guard)
        unattended_items = [
            str(item) for item in request.allowed_unattended_tools if str(item).strip()
        ]
        if skip_confirm and not unattended_items:
            set_unattended_tools(frozenset(["*"]))
        else:
            set_unattended_tools(frozenset(unattended_items))

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
        session.runtime_config = runtime_config

        # Durable run ids live under production_tasks; history child writes
        # (steps/artifacts) need the same id under sessions/.../runs. Create
        # that parent doc BEFORE the orchestrator starts writing children.
        if history_repository:
            try:
                await history_repository.ensure_run(
                    session_id=session.id,
                    run_id=request.run_id,
                    owner_id=request.owner_id,
                    title=request.title or "Agent Turn",
                    task_id=request.task_id,
                    status="queued",
                )
            except Exception:
                logger.exception(
                    "Failed to ensure history run %s for durable task %s",
                    request.run_id,
                    request.task_id,
                )

        async def activate_sandbox() -> None:
            await self.session_manager.activate_session(session.id)

        orchestrator = NexusOrchestrator(
            session=session,
            ws=WorkerEventWebSocket(),
            history_repository=history_repository,
            production_task_repository=self.production_task_repository,
            ensure_sandbox_ready=activate_sandbox,
        )
        cancel_watcher = asyncio.create_task(
            self._watch_for_cancel(orchestrator, request.task_id, request.owner_id)
        )
        try:
            await orchestrator.initialize(lazy_sandbox=True)
            orchestrator.restore_durable_checkpoint(request.checkpoint)
            resume_context = self._resume_context(request.checkpoint)
            # On resume the user turn already exists (first attempt / ws
            # transcript event); never re-show or re-persist it, and never let
            # the checkpoint block leak into the chat as a user message.
            emit_user_transcript = (
                request.emit_user_transcript and not resume_context
            )
            input_text = request.input_text
            if skip_confirm:
                directive = (
                    "[UNATTENDED SCHEDULED TASK - AUTO-APPROVAL ACTIVE]\n"
                    "This task is running on an automated schedule with skip confirmations enabled.\n"
                    "- DO NOT ask questions or call ask_choice / suggest_options. The user is not available to answer.\n"
                    "- DO NOT ask for confirmation or approval. All permissions and approvals are automatically granted.\n"
                    "- Make reasonable assumptions and proceed autonomously to complete the work.\n\n"
                )
                if not resume_context:
                    input_text = directive + request.input_text
                else:
                    resume_context = directive + resume_context

            turn_task = asyncio.create_task(
                orchestrator.handle_text_input(
                    input_text,
                    connector_ids=request.connector_ids,
                    tool_ids=request.tool_ids,
                    uploaded_files=request.uploaded_files,
                    emit_user_transcript=emit_user_transcript,
                    resume_context=resume_context or None,
                )
            )
            done, _ = await asyncio.wait(
                {turn_task},
                timeout=max(0.0, budget_guard.remaining_runtime_seconds),
            )
            if not done:
                budget_guard.exhaust_runtime()
                orchestrator._budget_stop_requested = True
                orchestrator._budget_stop_reason = budget_guard.exhausted_reason
                turn_task.cancel()
                await asyncio.gather(turn_task, return_exceptions=True)
                checkpoint = orchestrator._durable_checkpoint_payload(
                    reason="runtime_budget_exhausted",
                    verification={
                        "verified": False,
                        "status": "partial",
                        "method": "budget",
                        "summary": budget_guard.exhausted_reason,
                        "error_code": budget_guard.exhausted_code,
                        "remaining_work": [
                            "Resume from this checkpoint with a renewed budget."
                        ],
                        "retryable": False,
                    },
                )
                await self.production_task_repository.save_checkpoint(
                    task_id=request.task_id,
                    run_id=request.run_id,
                    owner_id=request.owner_id,
                    checkpoint=checkpoint,
                )
                return AgentTurnOutcome(
                    status="partial",
                    summary=budget_guard.exhausted_reason,
                    verification=checkpoint["verification"],
                    checkpoint=checkpoint,
                    retryable=False,
                )
            await turn_task
            turn_result = dict(orchestrator.last_turn_result or {})
            checkpoint = orchestrator._durable_checkpoint_payload(
                reason="turn_finished",
                verification=(
                    turn_result.get("verification")
                    if isinstance(turn_result.get("verification"), dict)
                    else {}
                ),
            )
            try:
                await self.production_task_repository.save_checkpoint(
                    task_id=request.task_id,
                    run_id=request.run_id,
                    owner_id=request.owner_id,
                    checkpoint=checkpoint,
                )
            except Exception:
                logger.warning(
                    "Failed to persist turn checkpoint for %s/%s",
                    request.task_id,
                    request.run_id,
                    exc_info=True,
                )
            if turn_result:
                verification = (
                    turn_result.get("verification")
                    if isinstance(turn_result.get("verification"), dict)
                    else {}
                )
                # Delivered-with-caveat is terminal success: normalize any legacy
                # "completed_with_caveat" to "completed" so the durable worker
                # finishes the run once and never re-enqueues a retry.
                normalized_status = str(turn_result.get("status") or "failed")
                if normalized_status == "completed_with_caveat":
                    normalized_status = "completed"
                return AgentTurnOutcome(
                    status=normalized_status,
                    summary=str(turn_result.get("summary") or ""),
                    final_response=str(turn_result.get("final_response") or ""),
                    verification=verification,
                    checkpoint=checkpoint,
                    retryable=bool(verification.get("retryable")),
                )

            durable_status = map_history_status_to_durable(session.run_status)
            if durable_status in {"failed", "cancelled"}:
                return AgentTurnOutcome(
                    durable_status,
                    f"Agent turn {durable_status}.",
                    checkpoint=checkpoint,
                )
            if cancel_watcher.done() and not cancel_watcher.cancelled():
                return AgentTurnOutcome(
                    "cancelled",
                    "Agent turn cancelled by user.",
                    checkpoint=checkpoint,
                )
            return AgentTurnOutcome(
                "failed",
                "Agent turn ended without a typed outcome.",
                checkpoint=checkpoint,
            )
        finally:
            clear_unattended_tools()
            set_task_budget_guard(None)
            cancel_watcher.cancel()
            try:
                await cancel_watcher
            except (asyncio.CancelledError, Exception):
                pass
            await orchestrator.close()

    @staticmethod
    def _resume_context(checkpoint: dict[str, Any]) -> str:
        """Build the durable-resume checkpoint block for the model.

        Returns only the checkpoint directive (no user text). Callers feed this
        to the model via ``resume_context`` so it is never shown or persisted
        as a user message.
        """
        if not checkpoint:
            return ""
        ledger = checkpoint.get("action_ledger")
        records = (
            ledger.get("records", [])
            if isinstance(ledger, dict)
            else []
        )
        completed = []
        for record in records[-12:]:
            if not isinstance(record, dict):
                continue
            decision = record.get("decision")
            observation = record.get("observation")
            if not isinstance(decision, dict) or not isinstance(observation, dict):
                continue
            completed.append(
                f"{decision.get('action', 'tool')}: "
                f"{observation.get('status', 'unknown')}"
            )
        if not completed:
            completed_text = "No completed action records were restored."
        else:
            completed_text = "; ".join(completed)
        approval = checkpoint.get("approval_resolution")
        approval_text = ""
        if isinstance(approval, dict):
            tool_name = str(approval.get("tool") or "the blocked action")
            if approval.get("approved"):
                canonical = approval.get("canonical_args") or {}
                args_hint = ""
                if isinstance(canonical, dict) and canonical:
                    rendered = ", ".join(
                        f"{key}={value!r}"
                        for key, value in list(canonical.items())[:8]
                    )
                    args_hint = f" Exact approved arguments: {rendered}."
                approval_text = (
                    f" Approval for {tool_name} was granted.{args_hint} "
                    "Re-issue that exact same tool call once; the gateway will "
                    "consume the stored approval by action hash and must not "
                    "ask again."
                )
            else:
                approval_text = (
                    f" Approval for {tool_name} was denied; do not retry that "
                    "exact action without a new user decision."
                )
        subagent_state = checkpoint.get("subagents")
        subagent_text = ""
        if isinstance(subagent_state, dict) and subagent_state:
            summaries = []
            for subagent_id, state in list(subagent_state.items())[:12]:
                status = (
                    state.get("status", "unknown")
                    if isinstance(state, dict)
                    else "unknown"
                )
                summaries.append(f"{subagent_id}:{status}")
            subagent_text = (
                " Durable subagents: "
                + ", ".join(summaries)
                + ". List and collect these records before spawning new work."
            )
        return (
            "[DURABLE RESUME CHECKPOINT]\n"
            "Previously recorded actions: "
            + completed_text
            + "."
            + approval_text
            + subagent_text
            + ". Continue from verified evidence. Do not repeat an external "
            "side effect unless its exact approval remains valid and unconsumed."
        )

    async def _watch_for_cancel(
        self,
        orchestrator: NexusOrchestrator,
        task_id: str,
        owner_id: str,
    ) -> None:
        """Poll the durable task for a user cancel request and stop the run.

        The user's stop button reaches Firestore (via WS handler or the REST
        cancel endpoint); a worker-owned run has no live WebSocket, so this
        watcher is what turns that flag into an actual stop.
        """
        while True:
            await asyncio.sleep(_CANCEL_POLL_SECONDS)
            try:
                task = await self.production_task_repository.get_task(task_id)
            except Exception:
                logger.debug("Cancel watcher poll failed for task %s", task_id, exc_info=True)
                continue
            if task is None or task.owner_id != owner_id:
                continue
            if task.cancel_requested or task.status in {"cancelling", "cancelled"}:
                logger.info("Cancel requested for durable task %s — stopping run", task_id)
                try:
                    await orchestrator.stop_agent()
                except Exception:
                    logger.warning("Failed to stop cancelled durable run %s", task_id, exc_info=True)
                return


class WorkerEventWebSocket:
    """No-op WebSocket facade used by durable workers."""

    client_state = WebSocketState.CONNECTED
    application_state = WebSocketState.CONNECTED

    async def send_json(self, data: dict) -> None:
        return None

    async def send_bytes(self, data: bytes) -> None:
        return None
