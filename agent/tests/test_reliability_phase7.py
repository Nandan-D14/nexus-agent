# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Reliability roadmap phase 7: benchmark suites and answer scoring."""

from __future__ import annotations

from nexus.eval.benchmarks import BENCHMARK_SUITES, GAIA_MINI, OSWORLD_MINI, validate_benchmarks
from nexus.eval.production_suite import TaskRunObservation, ToolObservation, build_report, score_case
from nexus.eval.run_task_eval import main


def _observation(case, *, response: str, verified: bool = False, tools=(), sources=()) -> TaskRunObservation:
    return TaskRunObservation(
        case_id=case.case_id,
        status="completed",
        final_response=response,
        expected_state_verified=verified,
        tool_steps=tuple(ToolObservation(name=name) for name in tools),
        source_urls=tuple(sources),
    )


def test_suites_have_expected_sizes() -> None:
    validate_benchmarks()
    assert len(GAIA_MINI) == 30 and len(OSWORLD_MINI) == 20
    assert set(BENCHMARK_SUITES) == {"gaia_mini", "osworld_mini"}
    assert all(case.expected_answers for case in GAIA_MINI)


def test_exact_answer_satisfies_state_verification() -> None:
    case = next(c for c in GAIA_MINI if c.case_id == "gaia-sum-100")
    good = score_case(case, _observation(case, response="The sum is 5050.", tools=("run_command",)))
    assert good.passed, good.failure_reasons
    wrong = score_case(case, _observation(case, response="The sum is 5000.", tools=("run_command",)))
    assert not wrong.passed
    assert "expected answer not found in final response" in wrong.failure_reasons


def test_build_report_accepts_benchmark_suite() -> None:
    observations = [
        _observation(case, response=" ".join(case.expected_answers), verified=True,
                     tools=case.expected_tool_order[0][:1] if case.expected_tool_order else (),
                     sources=("https://example.org",))
        for case in GAIA_MINI
    ]
    report = build_report(observations, run_id="t", run_mode="replay", cases=GAIA_MINI)
    assert report.summary.total == 30
    assert report.summary.passed == 30


def test_cli_validate_covers_benchmarks(capsys) -> None:
    assert main(["validate"]) == 0
    out = capsys.readouterr().out
    assert "gaia_mini=30" in out and "osworld_mini=20" in out
