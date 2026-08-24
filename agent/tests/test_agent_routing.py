# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Regression tests for the sole production planner path."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nexus.agent as agent_module
from nexus.agent import create_planner_agent
from nexus.config import Settings
from nexus.runtime_config import SessionRuntimeConfig


def _runtime_config() -> SessionRuntimeConfig:
    return SessionRuntimeConfig(
        e2b_api_key="test-e2b",
        gemini_provider="apiKey",
        gemini_api_key="",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model="",
        gemini_agent_fallback_models=(),
        gemini_light_model="",
        gemini_live_model="",
        gemini_live_region="us-central1",
        gemini_vision_model="",
        gemini_vision_fallback_models=(),
        qwen_planner_model="qwen3.6-max-preview",
        qwen_worker_model="qwen3-coder-plus",
        qwen_visual_model="qwen3-vl-plus",
        qwen_micro_model="qwen-flash",
        qwen_vision_model="qwen3-vl-plus",
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
    )


def _tool_names(agent) -> set[str]:
    return {
        str(getattr(tool, "name", "") or getattr(tool, "__name__", ""))
        for tool in list(getattr(agent, "tools", []) or [])
    }


class SinglePlannerRoutingTests(TestCase):
    def test_legacy_factories_and_runtime_flag_are_removed(self) -> None:
        self.assertFalse(hasattr(agent_module, "create_multi_agent"))
        self.assertFalse(hasattr(agent_module, "create_agent"))
        self.assertNotIn("use_multi_agent", Settings.model_fields)

    def test_planner_has_workers_without_transfer_sub_agents(self) -> None:
        planner = create_planner_agent(_runtime_config())
        names = _tool_names(planner)

        self.assertIn("terminal_worker", names)
        self.assertIn("desktop_worker", names)
        self.assertFalse(list(getattr(planner, "sub_agents", []) or []))
        self.assertNotIn("transfer_to_agent", str(planner.instruction))

    def test_task_override_changes_only_qwen_planner_tier(self) -> None:
        planner = create_planner_agent(
            _runtime_config(),
            task_model_override="qwen-plus",
        )
        self.assertIn("qwen-plus", str(planner.model))

    def test_legacy_orchestrator_module_is_deleted(self) -> None:
        legacy_path = (
            Path(__file__).resolve().parents[1]
            / "nexus"
            / "agents"
            / "orchestrator_agent.py"
        )
        self.assertFalse(legacy_path.exists())

    def test_legacy_transfer_mesh_factories_raise(self) -> None:
        from nexus.agents import sub_agents

        with self.assertRaisesRegex(RuntimeError, "create_browser_agent was removed"):
            sub_agents.create_browser_agent(_runtime_config())
        with self.assertRaisesRegex(RuntimeError, "create_deepresearcher_agent was removed"):
            sub_agents.create_deepresearcher_agent(_runtime_config())
        self.assertNotIn("Firefox", sub_agents.BROWSER_AGENT_PROMPT)
        self.assertIn("Chromium", sub_agents.BROWSER_AGENT_PROMPT)
