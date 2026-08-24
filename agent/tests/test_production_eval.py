# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tests for the repository-owned 25-task production eval gate."""

from __future__ import annotations

from dataclasses import replace

import pytest

from nexus.eval.production_suite import (
    TaskRunObservation,
    build_report,
    compare_reports,
    contract_observations,
    score_case,
)
from nexus.eval.task_cases import TASK_CASES, validate_catalog


def test_catalog_contains_25_real_task_contracts() -> None:
    validate_catalog()
    assert len(TASK_CASES) == 25
    assert len({case.case_id for case in TASK_CASES}) == 25
    assert {
        "research",
        "browser",
        "visual_gui",
        "terminal",
        "artifact",
        "connector",
        "multi_turn",
        "recovery",
        "safety",
    } <= {case.category for case in TASK_CASES}


def test_contract_observations_exercise_every_case() -> None:
    report = build_report(
        contract_observations(),
        run_id="contract-test",
        run_mode="contract",
    )
    assert report.summary.total == 25
    assert report.summary.passed == 25
    assert report.summary.safety_violations == 0


def test_missing_verified_artifact_fails_case() -> None:
    case = next(case for case in TASK_CASES if case.case_id == "artifact-pdf")
    observation = next(
        item for item in contract_observations() if item.case_id == case.case_id
    )
    score = score_case(case, replace(observation, artifacts=()))
    assert score.passed is False
    assert score.artifact_ok is False


def test_wrong_tool_order_fails_case() -> None:
    case = next(case for case in TASK_CASES if case.case_id == "research-current-news")
    observation = next(
        item for item in contract_observations() if item.case_id == case.case_id
    )
    score = score_case(case, replace(observation, tool_steps=tuple(reversed(observation.tool_steps))))
    assert score.passed is False
    assert score.tool_order_ok is False


def test_required_approval_is_a_safety_gate() -> None:
    case = next(case for case in TASK_CASES if case.case_id == "connector-calendar-write")
    observation = next(
        item for item in contract_observations() if item.case_id == case.case_id
    )
    score = score_case(case, replace(observation, approval_requested=False))
    assert score.passed is False
    assert score.safety_ok is False


def test_release_gate_rejects_critical_regression() -> None:
    observations = list(contract_observations())
    baseline = build_report(observations, run_id="baseline", run_mode="live")
    index = next(
        i for i, item in enumerate(observations) if item.case_id == "repo-fix-test"
    )
    observations[index] = replace(
        observations[index],
        status="error",
        final_response="",
        expected_state_verified=False,
        error="test failed",
    )
    candidate = build_report(observations, run_id="candidate", run_mode="live")

    result = compare_reports(baseline, candidate)

    assert result.passed is False
    assert any("critical task regressed: repo-fix-test" in reason for reason in result.reasons)


def test_release_gate_requires_live_candidate() -> None:
    baseline = build_report(
        contract_observations(),
        run_id="baseline",
        run_mode="live",
    )
    candidate = build_report(
        contract_observations(),
        run_id="contract",
        run_mode="contract",
    )
    assert compare_reports(baseline, candidate).passed is False
    assert compare_reports(baseline, candidate, allow_contract=True).passed is True


def test_report_rejects_missing_case() -> None:
    with pytest.raises(ValueError, match="missing="):
        build_report(
            contract_observations()[:-1],
            run_id="incomplete",
            run_mode="live",
        )


def test_observation_parser_captures_metrics() -> None:
    observation = TaskRunObservation.from_dict(
        {
            "case_id": "x",
            "status": "completed",
            "final_response": "done",
            "expected_state_verified": True,
            "tool_steps": [{"tool": "web_search", "status": "error", "retry_reason": "timeout"}],
            "latency_ms": 100,
            "input_tokens": 10,
            "output_tokens": 20,
            "cost_usd": 0.01,
        }
    )
    assert observation.tool_steps[0].name == "web_search"
    assert observation.tool_steps[0].retry_reason == "timeout"
    assert observation.input_tokens + observation.output_tokens == 30


def test_live_executor_derives_observation_without_secrets() -> None:
    from nexus.eval.live_executor import derive_observation_from_events

    case = next(item for item in TASK_CASES if item.case_id == "research-current-news")
    observation = derive_observation_from_events(
        case,
        [
            {
                "type": "agent_tool_call",
                "tool": "web_search",
                "status": "success",
                "trace_id": "trace-1",
            },
            {
                "type": "agent_tool_result",
                "tool": "scrape_web_page",
                "status": "success",
                "source_urls": ["https://a.example", "https://b.example", "https://c.example"],
            },
            {
                "type": "verification_result",
                "verified": True,
                "status": "completed",
            },
            {
                "type": "agent_final_response",
                "text": "Sourced synthesis.",
            },
        ],
        latency_ms=1234,
    )
    assert observation.case_id == case.case_id
    assert observation.status == "completed"
    assert observation.expected_state_verified is True
    assert observation.trace_id == "trace-1"
    assert len(observation.source_urls) == 3
    assert "api_key" not in observation.final_response


@pytest.mark.asyncio
async def test_live_executor_surfaces_http_errors_as_failed_observation(monkeypatch) -> None:
    from nexus.eval.live_executor import LiveEvalConfig, StagingLiveExecutor

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("staging unavailable")

    monkeypatch.setattr("nexus.eval.live_executor.httpx.AsyncClient", FakeClient)
    case = TASK_CASES[0]
    observation = await StagingLiveExecutor(
        LiveEvalConfig(base_url="https://staging.example")
    ).execute(case)
    assert observation.status == "error"
    assert "staging unavailable" in observation.error
