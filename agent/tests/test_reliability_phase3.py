# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Reliability roadmap phase 3: evidence-based completion verification."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from nexus.control_loop import (
    ActionDecision,
    ActionLedger,
    ActionObservation,
    verify_completion,
)


def _record(ledger: ActionLedger, action_id: str, tool: str, result: dict) -> None:
    ledger.start(ActionDecision.from_tool_call(action_id=action_id, tool_name=tool, arguments={}))
    ledger.finish(
        ActionObservation.from_tool_result(action_id=action_id, tool_name=tool, result=result)
    )


def _contract(status: str, **extra) -> dict:
    contract = {"status": status, "summary": "s", "claimed_artifacts": [], "evidence": [], "remaining": []}
    contract.update(extra)
    return {"status": "success", "summary": "Completion recorded", "metadata": {"completion_contract": contract}}


def test_worker_inner_gui_mutation_without_screenshot_is_stale() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        "w1",
        "desktop_worker",
        {
            "status": "success",
            "summary": "Clicked submit",
            "actions": [
                {"tool": "take_screenshot", "status": "success"},
                {"tool": "left_click", "status": "success"},
            ],
        },
    )
    result = verify_completion(request="submit the form", final_response="Form submitted.", ledger=ledger)
    assert result.error_code == "STALE_SCREEN_STATE"


def test_worker_inner_verification_after_mutation_passes() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        "w1",
        "desktop_worker",
        {
            "status": "success",
            "summary": "Clicked submit and confirmed",
            "actions": [
                {"tool": "left_click", "status": "success"},
                {"tool": "take_screenshot", "status": "success"},
            ],
        },
    )
    result = verify_completion(request="submit the form", final_response="Form submitted.", ledger=ledger)
    assert result.verified


def test_inner_failures_do_not_veto_a_recovered_worker() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        "w1",
        "terminal_worker",
        {
            "status": "success",
            "summary": "Installed deps after a retry",
            "actions": [{"tool": "run_command", "status": "error", "error_code": "TOOL_EXCEPTION"}],
        },
    )
    result = verify_completion(request="install deps", final_response="Dependencies installed.", ledger=ledger)
    assert result.verified


def test_inner_records_round_trip_through_checkpoint() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        "w1",
        "desktop_worker",
        {"status": "success", "summary": "x", "actions": [{"tool": "left_click", "status": "success"}]},
    )
    restored = ActionLedger.from_dict(ledger.to_dict())
    assert [r.inner for r in restored.records] == [False, True]
    assert not restored.has_fresh_gui_verification()
    assert "worker_actions" not in ledger.to_dict()["records"][0]["observation"]


def test_contract_claimed_artifact_must_exist() -> None:
    ledger = ActionLedger()
    _record(ledger, "c1", "report_completion", _contract("completed", claimed_artifacts=["outputs/report.pdf"]))
    result = verify_completion(request="hello", final_response="Done, see report.", ledger=ledger)
    assert result.error_code == "UNVERIFIED_ARTIFACT_CLAIM"


def test_contract_claim_backed_by_ledger_artifact_passes() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        "a1",
        "generate_pdf_report",
        {"status": "success", "summary": "PDF ready", "metadata": {"output_path": "/ws/outputs/report.pdf"}},
    )
    _record(ledger, "c1", "report_completion", _contract("completed", claimed_artifacts=["outputs/report.pdf"]))
    result = verify_completion(request="create a pdf report", final_response="Here is your report.", ledger=ledger)
    assert result.verified


def test_contract_partial_is_reported_not_success() -> None:
    ledger = ActionLedger()
    _record(ledger, "c1", "report_completion", _contract("blocked", remaining=["Connect Gmail"]))
    result = verify_completion(request="email the team", final_response="I need Gmail access.", ledger=ledger)
    assert not result.verified
    assert result.error_code == "REPORTED_BLOCKED"
    assert result.remaining_work == ["Connect Gmail"]

    from nexus.orchestrator import should_deliver_soft_veto

    assert should_deliver_soft_veto(
        deliver_enabled=True,
        final_response="I need Gmail access.",
        status=result.status,
        error_code=result.error_code,
    )


def test_contract_from_previous_turn_is_ignored() -> None:
    ledger = ActionLedger()
    _record(ledger, "c1", "report_completion", _contract("blocked", remaining=["x"]))
    ledger.advance_turn()
    result = verify_completion(request="thanks", final_response="You're welcome.", ledger=ledger)
    assert result.verified


def test_report_completion_tool_requires_remaining_for_partial() -> None:
    from nexus.tools.completion import report_completion

    bad = asyncio.run(report_completion(status="partial", summary="half"))
    assert bad["status"] == "error"
    good = asyncio.run(
        report_completion(status="completed", summary="ok", artifacts=["a.pdf"], evidence=["exit 0"])
    )
    contract = good["metadata"]["completion_contract"]
    assert contract["claimed_artifacts"] == ["a.pdf"]
    assert "artifacts" not in good["metadata"]


def test_gateway_records_inner_actions_into_worker_log() -> None:
    from nexus.tool_gateway import gated_tool
    from nexus.tools._context import begin_worker_action_log, end_worker_action_log

    async def take_screenshot() -> dict:
        return {"status": "success", "summary": "screen"}

    wrapped = gated_tool(take_screenshot)

    async def scenario():
        token = begin_worker_action_log()
        await wrapped()
        return end_worker_action_log(token)

    with patch("nexus.tool_gateway._check_verification_warning", return_value=None):
        actions = asyncio.run(scenario())
    assert actions == [{"tool": "take_screenshot", "status": "success", "error_code": ""}]


def test_preview_check_flags_dead_preview() -> None:
    from nexus import evidence_checks
    from nexus.config import settings

    ledger = ActionLedger()
    _record(
        ledger,
        "p1",
        "publish_app_preview",
        {"status": "success", "summary": "Preview", "metadata": {"artifacts": [{"url": "https://5173-x.e2b.app"}]}},
    )

    async def dead(client, url):
        return False

    with (
        patch.object(settings, "verify_preview_urls", True),
        patch.object(evidence_checks, "_reachable", dead),
    ):
        failure = asyncio.run(evidence_checks.check_preview_urls(ledger))
    assert failure is not None and failure.error_code == "PREVIEW_UNREACHABLE"
