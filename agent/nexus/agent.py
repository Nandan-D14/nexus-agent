# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""ADK planner construction and turn execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import re

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from nexus.config import settings
from nexus.control_loop import (
    looks_like_empty_summary,
    looks_like_slide_code_dump,
    looks_like_worker_envelope,
)
from nexus.runtime_config import SessionRuntimeConfig
from nexus.session_service import FirestoreSessionService
from nexus.turn_output import TurnOutput, finalization_pass, select_answer
from nexus.usage import (
    TokenUsageRecord,
    extract_token_usage_records,
    get_agent_usage_source,
)

logger = logging.getLogger(__name__)


def extract_answer_from_reasoning(text: str) -> str:
    """Return text outside ``<think>`` blocks, or "" when there is none.

    Guessing an answer from free-form reasoning paragraphs promoted the
    model's private planning to the user, so only explicit tags are honored.
    """
    if not text or not text.strip():
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    if cleaned and cleaned != text.strip():
        return cleaned
    return ""


# Instruction for the single tool-free finalization pass, used when the model
# finished a run with no user-visible answer (tool-only or reasoning-only).
_FINAL_SYNTHESIS_INSTRUCTION = (
    "The previous run produced no user-visible reply. Write the reply to the "
    "user's latest request now, using the tool results already in this "
    "conversation. Tools are off for this reply. If the requested deliverable "
    "is not finished, state plainly what exists (with links/paths), what is "
    "left, and why. Never answer with empty text or internal reasoning only."
)
# Bound the finalization pass; blocked tool calls count as rounds.
_SYNTHESIS_TURN_CAP = 2


@dataclass
class AgentTurnResult:
    response: str | None
    usage_records: list[TokenUsageRecord]
    error: str | None = None
    # True when the one tool-free finalization pass already ran this turn;
    # callers must not run another reply-only retry on top of it.
    finalization_pass_used: bool = False


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

    usage_records: list[TokenUsageRecord] = []
    usage_seen: set[tuple[str, str, int, int, int]] = set()
    max_turns = max_turns or settings.max_agent_turns
    usage_source, usage_model = get_agent_usage_source(runtime_config)
    unavailable_tool_note = ""

    async def _consume(new_message, turn_cap: int) -> tuple[TurnOutput, int]:
        """Drive the runner for one message; return its sorted output and rounds."""
        nonlocal unavailable_tool_note
        output = TurnOutput()
        rounds = 0
        run_kwargs: dict = {}
        if settings.stream_answer_deltas:
            from google.adk.agents.run_config import RunConfig, StreamingMode

            run_kwargs["run_config"] = RunConfig(streaming_mode=StreamingMode.SSE)
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
                **run_kwargs,
            ):
                if getattr(event, "partial", False) is True:
                    # Streamed chunk: display only. The aggregated event that
                    # follows carries the full text, tool calls, and usage, so
                    # partials never touch selection, rounds, or accounting.
                    if event_callback:
                        await event_callback(event)
                    continue
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

                output.observe(event)
                parts = getattr(getattr(event, "content", None), "parts", None) or []
                if any(getattr(part, "function_response", None) for part in parts):
                    # A call event is persisted before its tool runs. Stop
                    # only after the matching response arrives; breaking on
                    # the call leaves a permanent orphan in session history.
                    rounds += 1

                if rounds >= turn_cap:
                    logger.warning(
                        "Max completed tool rounds (%d) reached, stopping agent loop",
                        turn_cap,
                    )
                    break
        except ValueError as exc:
            # A hallucinated / unregistered tool name makes ADK's _get_tool raise
            # a bare ValueError. Do not let one bad tool call crash the whole turn.
            message_text = str(exc)
            lowered = message_text.lower()
            if "tool" in lowered and "not found" in lowered:
                logger.warning(
                    "Model requested an unavailable tool (%s); recovering gracefully for session %s",
                    message_text,
                    session_id,
                )
                unavailable_tool_note = (
                    "A requested tool was unavailable, so that action was skipped. "
                    "Continue using only the available tools."
                )
            else:
                raise
        return output, rounds

    # Never promote a raw worker/tool envelope, leaked slide-layout code, or an
    # empty lead-in stub: shipping them would deliver a void as the answer.
    def _promotable(text: str | None) -> bool:
        return bool(
            text
            and text.strip()
            and not looks_like_worker_envelope(text)
            and not looks_like_slide_code_dump(text)
            and not looks_like_empty_summary(text)
        )

    runtime_context = str(getattr(message, "runtime_context", "") or "")
    user_text = str(getattr(message, "user_text", message) or "")
    # Runtime facts and the user's words are separate parts: the model sees
    # which is which, and the user's text is never rewritten.
    parts = [types.Part(text=runtime_context)] if runtime_context else []
    if user_text or not parts:
        parts.append(types.Part(text=user_text))
    content = types.Content(role="user", parts=parts)
    output, turn_count = await _consume(content, max_turns)
    final_response = select_answer(output, promotable=_promotable)

    # One tool-free finalization pass when the run ended without an answer
    # (tool-only, reasoning-only, or a stub). Completed tools are not re-run.
    finalization_used = False
    if settings.force_final_synthesis and not final_response:
        finalization_used = True
        logger.warning(
            "No final text after %d tool round(s); running finalization pass for session %s",
            turn_count,
            session_id,
        )
        instruction = (synthesis_instruction or "").strip() or _FINAL_SYNTHESIS_INSTRUCTION
        synthesis_message = types.Content(
            role="user",
            parts=[types.Part(text=instruction)],
        )
        with finalization_pass():
            synth_output, _ = await _consume(synthesis_message, _SYNTHESIS_TURN_CAP)
        final_response = select_answer(synth_output, promotable=_promotable)
        if not final_response:
            reasoning = synth_output.last_reasoning or output.last_reasoning
            extracted = extract_answer_from_reasoning(reasoning)
            if _promotable(extracted):
                final_response = extracted

    if not final_response:
        extracted = extract_answer_from_reasoning(output.last_reasoning)
        if _promotable(extracted):
            final_response = extracted
    if not final_response and unavailable_tool_note:
        final_response = unavailable_tool_note

    return AgentTurnResult(
        response=final_response,
        usage_records=usage_records,
        finalization_pass_used=finalization_used,
    )
