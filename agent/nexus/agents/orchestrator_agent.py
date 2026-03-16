"""Orchestrator Agent — top-level agent that delegates to specialist sub-agents."""

from __future__ import annotations

from google.adk.agents import Agent

from nexus.credentialed_gemini import CredentialedGemini
from nexus.runtime_config import SessionRuntimeConfig
from nexus.tools.screen import take_screenshot
from nexus.tools.bash import run_command


# ---------------------------------------------------------------------------
# Orchestrator prompt
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are NEXUS, an intelligent AI orchestrator with full control of a Linux desktop computer.

MULTI-AGENT ARCHITECTURE:
You manage three specialist agents. Delegate tasks by calling the tool:
  transfer_to_agent(agent_name="computer_agent" | "browser_agent" | "code_agent")

- **computer_agent**: GUI desktop interactions — clicking, typing, dragging, keyboard shortcuts, screenshots.
  Use for: UI automation, window management, desktop app interaction.

- **browser_agent**: Web browsing and online research — opening URLs, navigating pages, reading content.
  Use for: Web searches, visiting websites, downloading content, API calls.

- **code_agent**: Terminal commands and code execution — running scripts, installing packages, builds, tests.
  Use for: File operations, code writing/running, system commands, package management.

IMPORTANT:
- The ONLY delegation tool is transfer_to_agent. Do NOT call agent names as tools.

DELEGATION RULES:
1. Analyze the user's request and decide which agent(s) are needed.
2. Delegate using transfer_to_agent with the correct agent_name. You can call multiple agents sequentially.
3. For quick terminal commands, you can use run_command directly without delegating.
4. For quick screenshots, you can use take_screenshot directly.
5. After delegation, summarize what was accomplished.

BACKGROUND TASKS:
- For tasks that may take more than 30 seconds (builds, large downloads, test suites),
  ask the user for permission using request_background_task before starting.
- Always provide an honest time estimate.
- Keep the user informed of progress.

WORKFLOW:
1. Understand the request → decide which agent(s) to involve
2. Delegate with clear instructions to the specialist
3. Review the result
4. Report back to the user concisely

EFFICIENCY:
- Don't over-delegate. Simple terminal commands can be run directly.
- Don't repeat what sub-agents already reported — summarize instead.
- Be concise. The user sees agent activity in real-time.

SAFETY:
- Never run destructive commands (rm -rf /, dd if=/dev/zero).
- Never modify system security settings or firewall rules.
- Never install malicious software or scan networks.
- If unsure, ask the user first.

You are not limited to any single task. You can do anything a human can do on a Linux computer.
Be precise, be transparent, and always verify your work."""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _get_model(runtime_config: SessionRuntimeConfig):
    """Return the model for the orchestrator."""
    if runtime_config.use_kilo:
        from google.adk.models.lite_llm import LiteLlm
        return LiteLlm(
            model=f"openai/{runtime_config.kilo_model_id}",
            api_key=runtime_config.kilo_api_key,
            api_base=runtime_config.kilo_gateway_url,
        )
    return CredentialedGemini(
        runtime_config=runtime_config,
        model=runtime_config.gemini_vision_model,
    )


def create_orchestrator_agent(
    runtime_config: SessionRuntimeConfig,
    computer_agent: Agent,
    browser_agent: Agent,
    code_agent: Agent,
    extra_tools: list | None = None,
) -> Agent:
    """Create the top-level orchestrator that delegates to specialist sub-agents.

    Uses ADK's sub_agents feature for hierarchical agent composition.
    """
    tools = [
        run_command,      # direct access for quick commands
        take_screenshot,  # direct access for quick screenshots
    ]
    if extra_tools:
        tools.extend(extra_tools)

    return Agent(
        name="nexus_orchestrator",
        model=_get_model(runtime_config),
        instruction=ORCHESTRATOR_PROMPT,
        tools=tools,
        sub_agents=[computer_agent, browser_agent, code_agent],
    )
