from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.agent import create_multi_agent
from nexus.runtime_config import SessionRuntimeConfig


def _tool_names(agent) -> list[str]:
    return [
        str(getattr(tool, "name", getattr(tool, "__name__", "")))
        for tool in getattr(agent, "tools", [])
    ]


def _runtime_config() -> SessionRuntimeConfig:
    return SessionRuntimeConfig(
        e2b_api_key="test-e2b",
        gemini_provider="apiKey",
        gemini_api_key="test-gemini",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model="gemini-test",
        gemini_agent_fallback_models=(),
        gemini_light_model="gemini-light-test",
        gemini_live_model="gemini-live-test",
        gemini_live_region="us-central1",
        gemini_vision_model="gemini-vision-test",
        gemini_vision_fallback_models=("gemini-vision-fallback",),
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
    )


class AgentRoutingPolicyTests(TestCase):
    def setUp(self) -> None:
        self.agent = create_multi_agent(_runtime_config())
        self.sub_agents = {agent.name: agent for agent in self.agent.sub_agents}

    def test_orchestrator_has_no_direct_shell_or_vision_tools(self) -> None:
        tool_names = _tool_names(self.agent)

        self.assertNotIn("run_command", tool_names)
        self.assertNotIn("take_screenshot", tool_names)
        self.assertIn("request_background_task", tool_names)

    def test_sub_agent_tool_surfaces_match_cli_first_policy(self) -> None:
        computer_tools = _tool_names(self.sub_agents["computer_agent"])
        browser_tools = _tool_names(self.sub_agents["browser_agent"])
        code_tools = _tool_names(self.sub_agents["code_agent"])

        self.assertIn("take_screenshot", computer_tools)
        self.assertNotIn("run_command", computer_tools)
        self.assertNotIn("open_browser", computer_tools)

        self.assertIn("open_browser", browser_tools)
        self.assertIn("run_command", browser_tools)

        self.assertIn("run_command", code_tools)
        self.assertIn("take_screenshot", code_tools)

    def test_orchestrator_prompt_enforces_routing_order(self) -> None:
        instruction = self.agent.instruction.lower()

        self.assertIn("code_agent is the first choice for terminal and file-system tasks", instruction)
        self.assertIn("browser_agent is for web tasks", instruction)
        self.assertIn("computer_agent is only for gui or visual tasks", instruction)
        self.assertIn("start with code_agent, then hand off to browser_agent", instruction)
        self.assertIn("do not send work to computer_agent just to look around", instruction)

    def test_sub_agent_prompts_lock_in_escalation_rules(self) -> None:
        computer_instruction = self.sub_agents["computer_agent"].instruction.lower()
        browser_instruction = self.sub_agents["browser_agent"].instruction.lower()
        code_instruction = self.sub_agents["code_agent"].instruction.lower()

        self.assertIn("only for tasks that truly require gui or visual state", computer_instruction)
        self.assertIn("do not use screenshots just to explore", computer_instruction)

        self.assertIn("you are only for browser and website tasks", browser_instruction)
        self.assertIn("local repo, file-system, and non-web terminal tasks; those belong to code_agent", browser_instruction)
        self.assertIn("use run_command only for narrow helper cases", browser_instruction)

        self.assertIn("start with shell and file inspection before any screenshot", code_instruction)
        self.assertIn("take_screenshot() is a last resort", code_instruction)
        self.assertIn("if the task is actually web navigation or web reading, return control for browser_agent", code_instruction)
