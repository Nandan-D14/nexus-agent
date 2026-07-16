# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""ADK planner construction and turn execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from nexus.config import settings
from nexus.debug_trace import emit_debug_trace
from nexus.runtime_config import SessionRuntimeConfig
from nexus.session_service import FirestoreSessionService
from nexus.usage import (
    TokenUsageRecord,
    extract_token_usage_records,
    get_agent_usage_source,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentTurnResult:
    response: str | None
    usage_records: list[TokenUsageRecord]
    error: str | None = None


def _runtime_for_task_model(
    runtime_config: SessionRuntimeConfig,
    task_model_override: str | None = None,
) -> SessionRuntimeConfig:
    """Apply a Qwen planner-tier override to one turn."""
    if (
        not task_model_override
        or task_model_override == runtime_config.qwen_planner_model
    ):
        return runtime_config
    return replace(
        runtime_config,
        qwen_planner_model=task_model_override,
    )


def create_planner_agent(
    runtime_config: SessionRuntimeConfig,
    task_model_override: str | None = None,
    integration_tools: list | None = None,
    skill_instruction: str = "",
) -> Agent:
    """Create the sole production planner with AgentTool workers."""
    from nexus.agents.planner_agent import create_planner_agent as _build

    effective_runtime_config = _runtime_for_task_model(
        runtime_config,
        task_model_override,
    )
    return _build(
        effective_runtime_config,
        integration_tools=integration_tools,
        skill_instruction=skill_instruction,
        model_override=task_model_override,
    )


def create_runner(
    agent: Agent,
    session_service: BaseSessionService | None = None,
) -> tuple[Runner, BaseSessionService]:
    """Create a Runner for executing planner turns."""
    session_service = session_service or FirestoreSessionService()
    runner = Runner(
        agent=agent,
        app_name="nexus",
        session_service=session_service,
    )
    return runner, session_service


async def run_agent_turn(
    runner: Runner,
    session_service: BaseSessionService,
    session_id: str,
    user_id: str,
    message: str,
    runtime_config: SessionRuntimeConfig,
    event_callback=None,
    max_turns: int | None = None,
) -> AgentTurnResult:
    """Execute one planner turn and return its final text and usage."""
    adk_session = await session_service.get_session(
        app_name="nexus",
        user_id=user_id,
        session_id=session_id,
    )
    if adk_session is None:
        await session_service.create_session(
            app_name="nexus",
            user_id=user_id,
            session_id=session_id,
        )

    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )
    final_response = None
    usage_records: list[TokenUsageRecord] = []
    usage_seen: set[tuple[str, str, int, int, int]] = set()
    turn_count = 0
    function_response_count = 0
    max_turns = max_turns or settings.max_agent_turns
    usage_source, usage_model = get_agent_usage_source(runtime_config)
    emit_debug_trace(
        run_id=f"session:{session_id[-12:]}",
        hypothesis_id="H3",
        location="agent.py:run_agent_turn",
        message="agent_runner_started",
        data={
            "max_turns": max_turns,
            "usage_source": usage_source,
            "usage_model": usage_model,
            "event_callback_bound": event_callback is not None,
        },
    )

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        for record in extract_token_usage_records(
            event,
            default_source=usage_source,
            default_model=usage_model,
        ):
            fingerprint = (
                record.source,
                record.model,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
            )
            if fingerprint in usage_seen:
                continue
            usage_seen.add(fingerprint)
            usage_records.append(record)

        if event_callback:
            await event_callback(event)

        if event.content and event.content.parts:
            if any(part.function_call for part in event.content.parts):
                turn_count += 1
            function_response_count += sum(
                1
                for part in event.content.parts
                if getattr(part, "function_response", None)
            )

        if (
            event.is_final_response()
            and event.content
            and event.content.parts
        ):
            for part in event.content.parts:
                if part.text:
                    final_response = part.text
                    break

        if turn_count >= max_turns:
            logger.warning(
                "Max turns (%d) reached, stopping agent loop",
                max_turns,
            )
            break

    emit_debug_trace(
        run_id=f"session:{session_id[-12:]}",
        hypothesis_id="H3,H4",
        location="agent.py:run_agent_turn",
        message="agent_runner_finished",
        data={
            "function_call_rounds": turn_count,
            "function_response_count": function_response_count,
            "hit_turn_cap": turn_count >= max_turns,
            "final_response_present": final_response is not None,
            "final_response_chars": len(final_response or ""),
            "usage_record_count": len(usage_records),
        },
    )
    return AgentTurnResult(
        response=final_response,
        usage_records=usage_records,
    )
