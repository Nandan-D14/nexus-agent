"""ADK agent definition — the NEXUS brain.

Supports two modes:
  1. Single agent (default fallback) — one agent with all tools.
  2. Multi-agent orchestrator — hierarchical: Orchestrator → sub-agents.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from nexus.credentialed_gemini import CredentialedGemini
from nexus.config import settings
from nexus.prompts.system import SYSTEM_PROMPT
from nexus.runtime_config import SessionRuntimeConfig
from nexus.tools import ALL_TOOLS
from nexus.usage import TokenUsageRecord, extract_token_usage_records, get_agent_usage_source

if TYPE_CHECKING:
    from nexus.sandbox import SandboxManager

logger = logging.getLogger(__name__)


@dataclass
class AgentTurnResult:
    response: str | None
    usage_records: list[TokenUsageRecord]


def _get_model(runtime_config: SessionRuntimeConfig):
    """Return either a LiteLlm wrapper (Kilo) or a Gemini model string."""
    if runtime_config.use_kilo:
        from google.adk.models.lite_llm import LiteLlm
        logger.info("Using Kilo gateway model: %s", runtime_config.kilo_model_id)
        return LiteLlm(
            model=f"openai/{runtime_config.kilo_model_id}",
            api_key=runtime_config.kilo_api_key,
            api_base=runtime_config.kilo_gateway_url,
        )
    return CredentialedGemini(
        runtime_config=runtime_config,
        model=runtime_config.gemini_vision_model,
    )


def create_agent(runtime_config: SessionRuntimeConfig) -> Agent:
    """Create the single NEXUS ADK agent with all desktop control tools."""
    agent = Agent(
        name="nexus",
        model=_get_model(runtime_config),
        instruction=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
    )
    return agent


def create_multi_agent(runtime_config: SessionRuntimeConfig) -> Agent:
    """Create a hierarchical multi-agent system.

    Returns the top-level orchestrator agent which delegates to:
      - computer_agent (GUI interactions)
      - browser_agent (web browsing)
      - code_agent (terminal & code)
    """
    from nexus.agents import (
        create_browser_agent,
        create_code_agent,
        create_computer_agent,
        create_orchestrator_agent,
    )
    from nexus.tools.bg_task import request_background_task

    computer = create_computer_agent(runtime_config)
    browser = create_browser_agent(runtime_config)
    code = create_code_agent(runtime_config)

    orchestrator = create_orchestrator_agent(
        runtime_config=runtime_config,
        computer_agent=computer,
        browser_agent=browser,
        code_agent=code,
        extra_tools=[request_background_task],
    )
    logger.info("Multi-agent orchestrator created with sub-agents: computer, browser, code")
    return orchestrator


def create_runner(agent: Agent) -> tuple[Runner, InMemorySessionService]:
    """Create a Runner for executing agent turns."""
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="nexus",
        session_service=session_service,
    )
    return runner, session_service


async def run_agent_turn(
    runner: Runner,
    session_service: InMemorySessionService,
    session_id: str,
    user_id: str,
    message: str,
    runtime_config: SessionRuntimeConfig,
    event_callback=None,
) -> AgentTurnResult:
    """Execute a single agent turn with a user message.

    Calls event_callback(event) for each intermediate event so the caller
    can stream tool calls, thoughts, etc. to the frontend.

    Returns the agent's final text response, or None.
    """
    # Ensure ADK session exists
    adk_session = await session_service.get_session(
        app_name="nexus", user_id=user_id, session_id=session_id
    )
    if adk_session is None:
        adk_session = await session_service.create_session(
            app_name="nexus", user_id=user_id, session_id=session_id
        )

    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )

    final_response = None
    usage_records: list[TokenUsageRecord] = []
    usage_seen: set[tuple[str, str, int, int, int]] = set()
    turn_count = 0
    max_turns = settings.max_agent_turns
    usage_source, usage_model = get_agent_usage_source(runtime_config)

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

        # Count tool call rounds
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call:
                    turn_count += 1
                    break

        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_response = part.text
                    break

        if turn_count >= max_turns:
            logger.warning("Max turns (%d) reached, stopping agent loop", max_turns)
            if not final_response:
                final_response = "I've taken many steps on this task. Here's what I've done so far — let me know if you'd like me to continue."
            break

    return AgentTurnResult(response=final_response, usage_records=usage_records)
