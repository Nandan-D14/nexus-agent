# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools._node_tool import NodeTool
from google.adk.workflow import FunctionNode, JoinNode, START, Workflow
from google.genai import types

from nexus.adk_capabilities import assess_adk_task_api
from nexus.agent import create_planner_agent
from nexus.deep_research_workflow import (
    DeepResearchRequest,
    DeepResearchWorkflowResult,
    create_deep_research_workflow,
    create_deep_research_workflow_tool,
)
from nexus.runtime_config import SessionRuntimeConfig
from nexus.tools.base import tool_success


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
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
        qwen_planner_model="qwen3.6-max-preview",
        qwen_worker_model="qwen3-coder-plus",
        qwen_visual_model="qwen3-vl-plus",
        qwen_micro_model="qwen-flash",
        qwen_vision_model="qwen3-vl-plus",
    )


def test_workflow_shape_is_graph_based_and_model_free() -> None:
    workflow = create_deep_research_workflow()
    nodes = {node.name: node for node in workflow.graph.nodes}

    assert isinstance(workflow, Workflow)
    assert workflow.input_schema is DeepResearchRequest
    assert workflow.output_schema is DeepResearchWorkflowResult
    assert {
        "research_query_primary",
        "research_query_evidence",
        "research_query_counterpoints",
        "research_fan_in",
        "source_verification",
        "evidence_synthesis",
        "report_review",
        "report_publish",
    } <= set(nodes)
    assert isinstance(nodes["research_fan_in"], JoinNode)
    assert all(
        isinstance(node, (FunctionNode, JoinNode))
        for node in nodes.values()
        if node is not START
    )


@pytest.mark.asyncio
async def test_workflow_runs_fanout_review_and_publish_contract() -> None:
    async def fake_search(query: str, max_results: int = 5):
        del max_results
        branch = (
            "counter"
            if "criticism" in query
            else "evidence"
            if "evidence sources" in query
            else "primary"
        )
        results = [
            {
                "title": f"{branch} source {index}",
                "url": f"https://{branch}{index}.example.com/article",
                "snippet": f"Evidence from {branch} source {index}.",
            }
            for index in range(1, 3)
        ]
        return tool_success(
            f"Found {len(results)} results",
            results=results,
        )

    async def fake_scrape(url: str, output_basename: str | None = None):
        return tool_success(
            f"Scraped {url}",
            url=url,
            title=output_basename or "source",
            content=f"Verified detailed evidence captured from {url}.",
            saved_path=f"/workspace/sources/{output_basename}.md",
        )

    fake_publish = AsyncMock(
        return_value=tool_success(
            "Published report",
            artifact_id="artifact-1",
            path="outputs/report.html",
            url="https://artifacts.example/report.html",
        )
    )
    fake_write = AsyncMock(
        return_value=tool_success("Wrote report", path="outputs/report.md")
    )
    workflow = create_deep_research_workflow()
    sessions = InMemorySessionService()
    session = await sessions.create_session(
        app_name="workflow-test",
        user_id="user-1",
    )
    runner = Runner(
        app_name="workflow-test",
        node=workflow,
        session_service=sessions,
    )
    outputs = []

    with (
        patch(
            "nexus.deep_research_workflow.web_search",
            AsyncMock(side_effect=fake_search),
        ) as search,
        patch(
            "nexus.deep_research_workflow.scrape_web_page",
            AsyncMock(side_effect=fake_scrape),
        ) as scrape,
        patch(
            "nexus.deep_research_workflow.write_workspace_file",
            fake_write,
        ),
        patch(
            "nexus.deep_research_workflow.publish_html_artifact",
            fake_publish,
        ),
    ):
        async for event in runner.run_async(
            user_id="user-1",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=json.dumps(
                            {
                                "request": (
                                    "Compare durable agent architectures"
                                )
                            }
                        )
                    )
                ],
            ),
        ):
            if event.output is not None:
                outputs.append(event.output)
    await runner.close()

    result = DeepResearchWorkflowResult.model_validate(outputs[-1])
    assert result.status == "success"
    assert result.review["status"] == "passed"
    assert len(result.sources) == 6
    assert len(result.artifacts) == 2
    assert "[1]" in result.report
    assert search.await_count == 3
    assert scrape.await_count == 6
    assert fake_write.await_count == 1
    assert fake_publish.await_count == 1


@pytest.mark.asyncio
async def test_workflow_is_converted_to_long_running_node_tool() -> None:
    workflow = create_deep_research_workflow_tool()
    tool = NodeTool(node=workflow)
    declaration = tool._get_declaration()
    expected = DeepResearchWorkflowResult(
        status="success",
        summary="workflow complete",
    ).model_dump()
    tool_context = SimpleNamespace(
        function_call_id="call-1",
        branch="planner",
        run_node=AsyncMock(return_value=expected),
    )

    result = await tool.run_async(
        args={"request": "Research a production agent design"},
        tool_context=tool_context,
    )

    assert isinstance(workflow, Workflow)
    assert declaration.name == "deep_research_workflow"
    assert declaration.parameters_json_schema["required"] == ["request"]
    assert declaration.response_json_schema["type"] == "object"
    assert tool.is_long_running is True
    assert result["status"] == "success"
    tool_context.run_node.assert_awaited_once()


def test_planner_exposes_workflow_only_behind_pilot_flag() -> None:
    with (
        patch(
            "nexus.agents.planner_agent.settings.deep_research_workflow_enabled",
            True,
        ),
        patch(
            "nexus.bynara_router.get_bynara_router",
            return_value=SimpleNamespace(),
        ),
    ):
        planner = create_planner_agent(_runtime_config())
    names = {
        str(getattr(tool, "name", "") or getattr(tool, "__name__", ""))
        for tool in planner.tools
    }

    assert "deep_research_workflow" in names
    assert "normal chat" in planner.instruction
    assert not planner.sub_agents


def test_adk_240_task_api_is_explicitly_deferred() -> None:
    assessment = assess_adk_task_api()

    assert assessment.adk_version == "2.4.0"
    assert assessment.available is False
    assert assessment.task_mode_available is True
    assert assessment.task_package_exports == ()
    assert assessment.decision == "defer"
    assert "repository-owned durable execution" in assessment.reason
