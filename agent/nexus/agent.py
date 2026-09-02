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
from nexus.control_loop import looks_like_worker_envelope
from nexus.output_normalization import is_reasoning_part
from nexus.runtime_config import SessionRuntimeConfig
from nexus.session_service import FirestoreSessionService
from nexus.usage import (
    TokenUsageRecord,
    extract_token_usage_records,
    get_agent_usage_source,
)

logger = logging.getLogger(__name__)


# Instruction used when the model finished a turn with no user-visible answer
# (tool-only, or reasoning-only thinking parts). Keep working if the user asked
# to create/build something; otherwise write the reply now.
_FINAL_SYNTHESIS_INSTRUCTION = (
    "The previous turn produced no user-visible reply (reasoning-only or empty). "
    "Continue the user's last request now. If the latest user text is a short "
    "confirmation like 'continue', 'create it', or 'do it', finish the previous "
    "substantial request in this conversation — do not treat the confirmation "
    "as the whole task. If they asked to create, build, or publish something "
    "that is not done, use tools to do the work "
    "(write_workspace_file, terminal_worker, publish_app_preview, github_push). "
    "Then write a short status to the user. Never finish with empty text or "
    "internal reasoning only."
)
# Bound the forced continuation so a stray loop cannot run forever. 20 tool
# rounds is enough to resume a create/build after a reasoning-only stall.
_SYNTHESIS_TURN_CAP = 20


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
    synthesis_instruction: str | None = None,
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

    final_response = None
    usage_records: list[TokenUsageRecord] = []
    usage_seen: set[tuple[str, str, int, int, int]] = set()
    max_turns = max_turns or settings.max_agent_turns
    usage_source, usage_model = get_agent_usage_source(runtime_config)

    async def _consume(new_message, turn_cap: int):
        """Drive the runner for one message.

        Returns (final_text, last_text, rounds, response_count, hit_cap) where
        final_text is the strict ``is_final_response`` text and last_text is the
        last non-empty text part seen (used as a fallback when the model does
        not flag a final response).
        """
        final_text: str | None = None
        last_text: str | None = None
        rounds = 0
        response_count = 0
        hit_cap = False
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
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
                        rounds += 1
                    response_count += sum(
                        1
                        for part in event.content.parts
                        if getattr(part, "function_response", None)
                    )
                    for part in event.content.parts:
                        # Only genuine answer text may become the response.
                        # Skip parts EXPLICITLY marked as reasoning (thought=True
                        # or reasoning fields). Do NOT apply the reasoning_is_text
                        # blanket here: that heuristic is for routing the live
                        # think-log stream; final/last answer text is the answer.
                        if getattr(part, "text", None) and not is_reasoning_part(part):
                            last_text = part.text

                if (
                    event.is_final_response()
                    and event.content
                    and event.content.parts
                ):
                    for part in event.content.parts:
                        if part.text and not is_reasoning_part(part):
                            final_text = part.text
                            break

                if rounds >= turn_cap:
                    logger.warning(
                        "Max turns (%d) reached, stopping agent loop",
                        turn_cap,
                    )
                    hit_cap = True
                    break
        except ValueError as exc:
            # A hallucinated / unregistered tool name makes ADK's _get_tool raise
            # a bare ValueError. Do not let one bad tool call crash the whole turn:
            # log it, surface a recovery note, and let the caller fall back to
            # last_text / forced synthesis instead of propagating the exception.
            message = str(exc)
            lowered = message.lower()
            if "tool" in lowered and "not found" in lowered:
                logger.warning(
                    "Model requested an unavailable tool (%s); recovering gracefully for session %s",
                    message,
                    session_id,
                )
                if not (last_text and last_text.strip()):
                    last_text = (
                        "A requested tool was unavailable, so that action was skipped. "
                        "Continue using only the available tools."
                    )
            else:
                raise
        return final_text, last_text, rounds, response_count, hit_cap

    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )
    (
        final_response,
        last_text,
        turn_count,
        function_response_count,
        hit_turn_cap,
    ) = await _consume(content, max_turns)

    # Robust capture: if the model never flagged a strict final response, fall
    # back to the last text it emitted so a summary is not silently dropped.
    # Never promote a raw worker/tool result envelope — that must trigger
    # forced synthesis instead of leaking JSON into the user bubble.
    if looks_like_worker_envelope(final_response):
        final_response = None
    if not (final_response and final_response.strip()) and (
        last_text and last_text.strip() and not looks_like_worker_envelope(last_text)
    ):
        final_response = last_text

    # Forced final synthesis: empty answer after tools OR after a reasoning-only
    # turn with no user-visible text (thinking models often emit thought parts
    # and then stop, which used to skip this pass and fail the turn).
    forced_synthesis_used = False
    if settings.force_final_synthesis and not (final_response and final_response.strip()):
        forced_synthesis_used = True
        logger.warning(
            "No final text after %d tool round(s); forcing synthesis turn for session %s",
            turn_count,
            session_id,
        )
        instruction = (synthesis_instruction or "").strip() or _FINAL_SYNTHESIS_INSTRUCTION
        synthesis_message = types.Content(
            role="user",
            parts=[types.Part(text=instruction)],
        )
        synth_final, synth_last, _, _, _ = await _consume(
            synthesis_message,
            _SYNTHESIS_TURN_CAP,
        )
        if synth_final and synth_final.strip() and not looks_like_worker_envelope(synth_final):
            final_response = synth_final
        elif synth_last and synth_last.strip() and not looks_like_worker_envelope(synth_last):
            final_response = synth_last

    return AgentTurnResult(
        response=final_response,
        usage_records=usage_records,
    )
