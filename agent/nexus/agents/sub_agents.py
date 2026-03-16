"""Specialist sub-agents — each focused on a specific domain."""

from __future__ import annotations

from google.adk.agents import Agent

from nexus.credentialed_gemini import CredentialedGemini
from nexus.runtime_config import SessionRuntimeConfig
from nexus.tools.computer import (
    left_click,
    right_click,
    double_click,
    type_text,
    press_key,
    scroll_screen,
    drag,
)
from nexus.tools.screen import take_screenshot
from nexus.tools.bash import run_command
from nexus.tools.browser import open_browser

# ---------------------------------------------------------------------------
# Sub-agent system prompts (focused & narrow)
# ---------------------------------------------------------------------------

COMPUTER_AGENT_PROMPT = """You are the Computer Agent — a specialist for GUI desktop interactions.

CAPABILITIES:
- Click, double-click, right-click anywhere on screen (1024x768)
- Type text at the cursor position
- Press any key or key combination
- Scroll the screen
- Drag elements
- Take screenshots to verify actions

RULES:
- Prefer keyboard shortcuts over mouse navigation when possible.
- After important GUI actions, take a screenshot to verify.
- Report clearly what you did and what you observed.
- If an action fails, try ONE alternative approach before reporting.
- Keep responses concise.

COORDINATE SYSTEM:
- Screen resolution: 1024x768 pixels
- Origin (0, 0) is top-left
- Taskbar at bottom (~y=748), title bars at ~y=10
"""

BROWSER_AGENT_PROMPT = """You are the Browser Agent — a specialist for web browsing and research.

CAPABILITIES:
- Open URLs in Firefox (open_browser)
- Navigate web pages using keyboard shortcuts (Ctrl+L for address bar, Ctrl+T for new tab)
- Take screenshots to read page content
- Run curl/wget commands for API calls or downloads

WORKFLOW:
1. Use open_browser to navigate to URLs
2. Take screenshots to see page content
3. Use keyboard/mouse to interact with web pages
4. If vision is limited, use curl + text processing as fallback

RULES:
- Always verify page loaded by taking a screenshot after navigation
- Use terminal-based web access (curl, wget) for data extraction when more reliable
- Report findings clearly and concisely
"""

CODE_AGENT_PROMPT = """You are the Code Agent — a specialist for terminal commands and code execution.

CAPABILITIES:
- Run any shell command (run_command)
- Execute scripts in Python, Node.js, Bash, etc.
- Read and write files
- Install packages
- Run builds, tests, servers
- Take screenshots to verify GUI results of commands

RULES:
- For GUI applications, ALWAYS use run_command with background=True
- Chain safe commands with && when possible
- Show command output in your response
- If a command times out, retry with background=True
- Never run destructive commands (rm -rf /, dd if=/dev/zero, etc.)
- Keep responses concise — show relevant output only
"""


# ---------------------------------------------------------------------------
# Sub-agent factories
# ---------------------------------------------------------------------------

def _get_model(runtime_config: SessionRuntimeConfig):
    """Return the model identifier for sub-agents."""
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


def create_computer_agent(runtime_config: SessionRuntimeConfig) -> Agent:
    """Create the Computer Agent for GUI interactions."""
    return Agent(
        name="computer_agent",
        model=_get_model(runtime_config),
        instruction=COMPUTER_AGENT_PROMPT,
        tools=[
            take_screenshot,
            left_click,
            right_click,
            double_click,
            type_text,
            press_key,
            scroll_screen,
            drag,
        ],
    )


def create_browser_agent(runtime_config: SessionRuntimeConfig) -> Agent:
    """Create the Browser Agent for web browsing and research."""
    return Agent(
        name="browser_agent",
        model=_get_model(runtime_config),
        instruction=BROWSER_AGENT_PROMPT,
        tools=[
            open_browser,
            take_screenshot,
            run_command,
            left_click,
            type_text,
            press_key,
            scroll_screen,
        ],
    )


def create_code_agent(runtime_config: SessionRuntimeConfig) -> Agent:
    """Create the Code Agent for terminal commands and code execution."""
    return Agent(
        name="code_agent",
        model=_get_model(runtime_config),
        instruction=CODE_AGENT_PROMPT,
        tools=[
            run_command,
            take_screenshot,
            type_text,
            press_key,
        ],
    )
