from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.agent import create_agent, create_multi_agent
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
        self.single_agent = create_agent(_runtime_config())
        self.agent = create_multi_agent(_runtime_config())
        self.sub_agents = {agent.name: agent for agent in self.agent.sub_agents}
        self.deepresearcher = self.sub_agents["deepresearcher"]
        self.research_sub_agent_names = [agent.name for agent in self.deepresearcher.sub_agents]
        self.research_sub_agents = {
            agent.name: agent for agent in self.deepresearcher.sub_agents
        }

    def test_orchestrator_has_no_direct_shell_or_vision_tools(self) -> None:
        tool_names = _tool_names(self.agent)

        self.assertNotIn("run_command", tool_names)
        self.assertNotIn("take_screenshot", tool_names)
        self.assertIn("request_background_task", tool_names)
        self.assertIn("prepare_task_workspace", tool_names)
        self.assertIn("write_todo_list", tool_names)
        self.assertIn("list_workspace_files", tool_names)

    def test_sub_agent_tool_surfaces_match_cli_first_policy(self) -> None:
        computer_tools = _tool_names(self.sub_agents["computer_agent"])
        browser_tools = _tool_names(self.sub_agents["browser_agent"])
        code_tools = _tool_names(self.sub_agents["code_agent"])
        deepresearcher_tools = _tool_names(self.deepresearcher)
        research_computer_tools = _tool_names(self.research_sub_agents["research_computer_agent"])
        research_browser_tools = _tool_names(self.research_sub_agents["research_browser_agent"])
        research_code_tools = _tool_names(self.research_sub_agents["research_code_agent"])
        single_agent_tools = _tool_names(self.single_agent)

        self.assertIn("take_screenshot", computer_tools)
        self.assertNotIn("run_command", computer_tools)
        self.assertNotIn("open_browser", computer_tools)
        self.assertIn("write_workspace_file", computer_tools)
        self.assertIn("write_todo_list", computer_tools)

        self.assertIn("open_browser", browser_tools)
        self.assertIn("run_command", browser_tools)
        self.assertIn("web_search", browser_tools)
        self.assertIn("scrape_web_page", browser_tools)
        self.assertIn("write_workspace_file", browser_tools)

        self.assertIn("run_command", code_tools)
        self.assertIn("take_screenshot", code_tools)
        self.assertIn("write_workspace_file", code_tools)
        self.assertIn("update_todo_item", code_tools)

        self.assertIn("request_background_task", deepresearcher_tools)
        self.assertIn("prepare_task_workspace", deepresearcher_tools)
        self.assertIn("write_workspace_file", deepresearcher_tools)
        self.assertNotIn("run_command", deepresearcher_tools)
        self.assertNotIn("take_screenshot", deepresearcher_tools)
        self.assertNotIn("open_browser", deepresearcher_tools)

        self.assertIn("take_screenshot", research_computer_tools)
        self.assertNotIn("run_command", research_computer_tools)
        self.assertNotIn("open_browser", research_computer_tools)
        self.assertIn("write_workspace_file", research_computer_tools)

        self.assertIn("open_browser", research_browser_tools)
        self.assertIn("run_command", research_browser_tools)
        self.assertIn("web_search", research_browser_tools)
        self.assertIn("scrape_web_page", research_browser_tools)

        self.assertIn("run_command", research_code_tools)
        self.assertIn("take_screenshot", research_code_tools)
        self.assertIn("write_workspace_file", research_code_tools)

        self.assertIn("prepare_task_workspace", single_agent_tools)
        self.assertIn("write_todo_list", single_agent_tools)
        self.assertIn("web_search", single_agent_tools)
        self.assertIn("scrape_web_page", single_agent_tools)
        self.assertIn("run_command", single_agent_tools)
        self.assertIn("take_screenshot", single_agent_tools)

    def test_orchestrator_prompt_enforces_routing_order(self) -> None:
        instruction = self.agent.instruction.lower()

        self.assertIn("code_agent is the first choice for terminal and file-system tasks", instruction)
        self.assertIn("browser_agent is for web tasks", instruction)
        self.assertIn("computer_agent is only for gui or visual tasks", instruction)
        self.assertIn("deepresearcher is for explicit deep-research tasks", instruction)
        self.assertIn("start with code_agent, then hand off to browser_agent", instruction)
        self.assertIn("start with deepresearcher", instruction)
        self.assertIn("do not send work to computer_agent just to look around", instruction)
        self.assertIn("research, summarization, report writing, and html dashboard generation are not gui tasks by themselves", instruction)
        self.assertIn("use computer_agent only to open the finished artifact", instruction)
        self.assertIn("research today's top global and indian news from at least five sources", instruction)
        self.assertIn("prepare_task_workspace", instruction)
        self.assertIn("write_todo_list", instruction)
        self.assertIn("refresh the todo list before delegating", instruction)

    def test_sub_agent_prompts_lock_in_escalation_rules(self) -> None:
        computer_instruction = self.sub_agents["computer_agent"].instruction.lower()
        browser_instruction = self.sub_agents["browser_agent"].instruction.lower()
        code_instruction = self.sub_agents["code_agent"].instruction.lower()
        deepresearcher_instruction = self.deepresearcher.instruction.lower()
        research_computer_instruction = self.research_sub_agents["research_computer_agent"].instruction.lower()
        research_browser_instruction = self.research_sub_agents["research_browser_agent"].instruction.lower()
        research_code_instruction = self.research_sub_agents["research_code_agent"].instruction.lower()
        single_instruction = self.single_agent.instruction.lower()

        self.assertIn("only for tasks that truly require gui or visual state", computer_instruction)
        self.assertIn("do not use screenshots just to explore", computer_instruction)
        self.assertIn("do not gather normal research sources or author the report in the gui", research_computer_instruction)
        self.assertIn("open or focus the finished file instead of re-authoring it in the gui", computer_instruction)
        self.assertIn("read task.md and todo.md", computer_instruction)
        self.assertIn("write_workspace_file(\"notes.md\"", computer_instruction)

        self.assertIn("you are only for browser and website tasks", browser_instruction)
        self.assertIn("local repo, file-system, and non-web terminal tasks; those belong to code_agent", browser_instruction)
        self.assertIn("use run_command only for narrow helper cases", browser_instruction)
        self.assertIn("use web_search(query) for discovery", browser_instruction)
        self.assertIn("scrape_web_page(url)", browser_instruction)
        self.assertIn("if the task asks for a generated html dashboard or report, gather sources and evidence here, then hand file creation to code_agent", browser_instruction)
        self.assertIn("if scrape_web_page returns an error such as 401, 403, or 429, treat that source as blocked instead of failing the whole task", browser_instruction)
        self.assertIn("prefer web_search and scrape_web_page over interactive browsing for normal research collection", research_browser_instruction)
        self.assertIn("if a source blocks scraping, record that it was blocked and continue with alternative sources", research_browser_instruction)

        self.assertIn("start with shell and file inspection before any screenshot", code_instruction)
        self.assertIn("take_screenshot() is a last resort", code_instruction)
        self.assertIn("if the task is actually web navigation or web reading, return control for browser_agent", code_instruction)
        self.assertIn("generating dashboards, reports, html files, and other workspace deliverables is code_agent work", code_instruction)
        self.assertIn("append concise findings to notes.md", code_instruction)
        self.assertIn("mark the step done with update_todo_item", code_instruction)

        self.assertIn("you are a coordinator only", deepresearcher_instruction)
        self.assertIn("delegate web and source gathering to research_browser_agent", deepresearcher_instruction)
        self.assertIn("delegate local repo, log, file, config, cli evidence-gathering, and final report or dashboard generation to research_code_agent", deepresearcher_instruction)
        self.assertIn("use request_background_task() before continuing", deepresearcher_instruction)
        self.assertIn("write or refresh a 3-7 step master todo list", deepresearcher_instruction)
        self.assertIn("save the final report to outputs/final.md", deepresearcher_instruction)
        self.assertIn("a request to research news, summarize it, categorize it, and generate an html dashboard is still a research-plus-code workflow, not a gui workflow", deepresearcher_instruction)
        self.assertIn("leave final open or visual confirmation to research_computer_agent only when explicitly needed", research_code_instruction)

        self.assertIn("only for tasks that truly require gui or visual state", research_computer_instruction)
        self.assertIn("do not use screenshots just to explore", research_computer_instruction)

        self.assertIn("you are only for browser and website tasks", research_browser_instruction)
        self.assertIn("use run_command only for narrow helper cases", research_browser_instruction)
        self.assertIn("use web_search(query) for discovery", research_browser_instruction)

        self.assertIn("start with shell and file inspection before any screenshot", research_code_instruction)
        self.assertIn("take_screenshot() is a last resort", research_code_instruction)
        self.assertIn("write deliverables into outputs/", research_code_instruction)
        self.assertEqual(
            self.research_sub_agent_names,
            ["research_browser_agent", "research_code_agent", "research_computer_agent"],
        )

        self.assertIn("start every request by calling prepare_task_workspace", single_instruction)
        self.assertIn("write a fresh 3-7 step plan with write_todo_list", single_instruction)
        self.assertIn("prefer run_command", single_instruction)
        self.assertIn("prefer web_search(...) and scrape_web_page(...)", single_instruction)
        self.assertIn("research, summarization, report writing, and html dashboard generation are not gui tasks by themselves", single_instruction)
