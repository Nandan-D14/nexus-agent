"""Multi-agent subsystem — hierarchical orchestration."""

from nexus.agents.sub_agents import (
    create_computer_agent,
    create_browser_agent,
    create_code_agent,
    create_deepresearcher_agent,
)
from nexus.agents.orchestrator_agent import create_orchestrator_agent

__all__ = [
    "create_computer_agent",
    "create_browser_agent",
    "create_code_agent",
    "create_deepresearcher_agent",
    "create_orchestrator_agent",
]
