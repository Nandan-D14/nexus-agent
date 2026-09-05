# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Planner shape tests (docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md).

After the migration the planner is the ONLY foreground agent — the artifact
mini-agent and the fast path were removed. These tests pin the planner's
tool surface, prompt triage sections, and worker isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.tools.agent_tool import AgentTool

from nexus.agent import create_planner_agent
from nexus.agents.planner_agent import BudgetedAgentTool, _parse_worker_result
from nexus.agents.sub_agents import create_desktop_worker, create_terminal_worker
from nexus.config import settings
from nexus.runtime_config import SessionRuntimeConfig
from nexus.subagents import SubagentSupervisor
from nexus.tools._context import increment_worker_call_count, reset_worker_call_count


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


class PlannerV2ShapeTests(TestCase):
    def setUp(self) -> None:
        self.runtime_config = _runtime_config()
        self.planner = create_planner_agent(self.runtime_config)
        self.terminal = create_terminal_worker(self.runtime_config)
        self.desktop = create_desktop_worker(self.runtime_config)

    def test_planner_has_no_sub_agents(self) -> None:
        self.assertFalse(getattr(self.planner, "sub_agents", None))

    def test_desktop_worker_registers_triple_click(self) -> None:
        # Guards against the model hallucinating triple_click and crashing the turn.
        self.assertIn("triple_click", _tool_names(self.desktop))
        self.assertIn("double_click", _tool_names(self.desktop))

    def test_planner_exposes_run_command_and_workers_not_vision(self) -> None:
        tool_names = _tool_names(self.planner)

        self.assertIn("run_command", tool_names)
        self.assertNotIn("take_screenshot", tool_names)
        self.assertIn("terminal_worker", tool_names)
        self.assertIn("desktop_worker", tool_names)
        self.assertIn("ask_choice", tool_names)
        self.assertIn("suggest_options", tool_names)
        self.assertIn("publish_html_artifact", tool_names)
        self.assertIn("publish_app_preview", tool_names)
        self.assertIn("invoke_subagent", tool_names)
        self.assertIn("read_skill", tool_names)
        self.assertIn("propose_workflow_template", tool_names)
        self.assertIn("update_workflow_template", tool_names)
        self.assertIn("publish_workflow_template", tool_names)

    def test_planner_worker_tools_are_budgeted_agent_tools(self) -> None:
        worker_tools = [
            tool
            for tool in self.planner.tools
            if getattr(tool, "name", "") in {"terminal_worker", "desktop_worker"}
        ]
        self.assertEqual(len(worker_tools), 2)
        for tool in worker_tools:
            self.assertIsInstance(tool, BudgetedAgentTool)

    def test_planner_prompt_uses_worker_briefs_not_transfers(self) -> None:
        instruction = self.planner.instruction.lower()
        self.assertIn("terminal_worker", instruction)
        self.assertIn("desktop_worker", instruction)
        self.assertIn("ask_choice", instruction)
        self.assertIn("suggest_options", instruction)
        self.assertIn("propose_workflow_template", instruction)
        self.assertIn("read_skill", instruction)
        self.assertIn("do not stop at raw search results", instruction)
        self.assertIn("never end a turn on a bare tool call", instruction)
        self.assertIn("run_command", instruction)
        self.assertIn("mcp__treg__", instruction)
        self.assertNotIn("transfer_to_agent", instruction)

    def test_planner_prompt_encodes_self_triage(self) -> None:
        instruction = self.planner.instruction.lower()
        self.assertIn("self-triage", instruction)
        self.assertIn("tools or not", instruction)
        self.assertIn("evidence or context", instruction)
        self.assertIn("deliverable", instruction)
        self.assertIn("skills", instruction)
        self.assertIn("generate_pdf_report", instruction)
        self.assertIn("generate_excel_report", instruction)
        self.assertIn("generate_docx_report", instruction)
        self.assertIn("generate_pptx_report", instruction)
        self.assertIn("publish_app_preview", instruction)

    def test_terminal_worker_surface_is_shell_and_files_only(self) -> None:
        tool_names = _tool_names(self.terminal)
        self.assertIn("run_command", tool_names)
        self.assertIn("generate_excel_report", tool_names)
        self.assertIn("generate_docx_report", tool_names)
        self.assertIn("generate_pptx_report", tool_names)
        self.assertIn("publish_app_preview", tool_names)
        self.assertNotIn("take_screenshot", tool_names)
        self.assertNotIn("open_browser", tool_names)

    def test_terminal_worker_prompt_forbids_secret_hunting(self) -> None:
        instruction = str(self.terminal.instruction).lower()
        self.assertIn("never run find /", instruction)
        self.assertIn("api keys", instruction)
        self.assertIn("this json", instruction)

    def test_missing_tool_result_becomes_typed_worker_interrupt(self) -> None:
        result = _parse_worker_result(
            "Error: Missing tool result (tool execution may have been interrupted "
            "before a response was recorded).",
            "terminal_worker",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "WORKER_TOOL_INTERRUPTED")
        self.assertTrue(result["retryable"])

    def test_desktop_worker_surface_is_gui_only(self) -> None:
        tool_names = _tool_names(self.desktop)
        self.assertIn("take_screenshot", tool_names)
        self.assertIn("open_browser", tool_names)
        self.assertIn("playwright_navigate", tool_names)
        self.assertNotIn("run_command", tool_names)

    def test_background_subagent_types_match_plan_surfaces(self) -> None:
        supervisor = SubagentSupervisor(
            runtime_config=self.runtime_config,
            session_service=MagicMock(),
            owner_id="user-1",
            parent_session_id="session-1",
            parent_run_id=None,
        )
        researcher = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in supervisor._tools_for_type("researcher")
        ]
        coder = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in supervisor._tools_for_type("coder")
        ]
        writer = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in supervisor._tools_for_type("writer")
        ]

        self.assertIn("web_search", researcher)
        self.assertIn("tavily_search", researcher)
        self.assertIn("write_workspace_file", researcher)
        self.assertIn("run_command", coder)
        self.assertIn("publish_html_artifact", writer)


class WorkerBudgetTests(IsolatedAsyncioTestCase):
    async def test_budgeted_agent_tool_blocks_after_limit(self) -> None:
        reset_worker_call_count()
        worker = create_terminal_worker(_runtime_config())
        tool = BudgetedAgentTool(agent=worker, skip_summarization=True)
        tool_context = MagicMock()

        with patch.object(AgentTool, "run_async", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"status": "success", "summary": "ok"}
            for _ in range(settings.max_worker_calls_per_turn):
                result = await tool.run_async(args={"request": "noop"}, tool_context=tool_context)
                self.assertNotEqual(result.get("error_code"), "WORKER_BUDGET_EXCEEDED")

            blocked = await tool.run_async(args={"request": "noop"}, tool_context=tool_context)
            self.assertEqual(blocked.get("error_code"), "WORKER_BUDGET_EXCEEDED")
            self.assertEqual(mock_run.await_count, settings.max_worker_calls_per_turn)

    async def test_budgeted_agent_tool_maps_deadline_exception_to_json(self) -> None:
        reset_worker_call_count()
        worker = create_terminal_worker(_runtime_config())
        tool = BudgetedAgentTool(agent=worker, skip_summarization=True)

        with patch.object(AgentTool, "run_async", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("Deadline Exceeded")
            result = await tool.run_async(args={"request": "noop"}, tool_context=MagicMock())

        self.assertEqual(result.get("error_code"), "WORKER_DEADLINE")
        self.assertTrue(result.get("retryable"))
        self.assertEqual(result.get("status"), "error")

    async def test_budgeted_agent_tool_maps_deadline_string_to_json(self) -> None:
        reset_worker_call_count()
        worker = create_terminal_worker(_runtime_config())
        tool = BudgetedAgentTool(agent=worker, skip_summarization=True)

        with patch.object(AgentTool, "run_async", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "504 Stream removed (Deadline Exceeded)"
            result = await tool.run_async(args={"request": "noop"}, tool_context=MagicMock())

        self.assertEqual(result.get("error_code"), "WORKER_DEADLINE")
        self.assertTrue(result.get("retryable"))

    async def test_budgeted_agent_tool_maps_plain_string_to_untyped(self) -> None:
        reset_worker_call_count()
        worker = create_terminal_worker(_runtime_config())
        tool = BudgetedAgentTool(agent=worker, skip_summarization=True)

        with patch.object(AgentTool, "run_async", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "worker printed prose instead of JSON"
            result = await tool.run_async(args={"request": "noop"}, tool_context=MagicMock())

        self.assertEqual(result.get("error_code"), "WORKER_RESULT_UNTYPED")
        self.assertTrue(result.get("retryable"))

    def test_worker_call_counter_resets_per_turn(self) -> None:
        reset_worker_call_count()
        self.assertEqual(increment_worker_call_count(), 1)
        reset_worker_call_count()
        self.assertEqual(increment_worker_call_count(), 1)
