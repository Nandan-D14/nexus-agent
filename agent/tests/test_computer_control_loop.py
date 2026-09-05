# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import pytest

from nexus.control_loop import (
    ActionDecision,
    ActionLedger,
    ActionObservation,
    verify_completion,
)
from nexus.subagent_resources import ToolResourceLocks
from nexus.tool_gateway import gated_tool
from nexus.tools import browser_playwright
from nexus.tools.screen_state import clear_dirty, is_dirty, mark_dirty


def _record(
    ledger: ActionLedger,
    *,
    action_id: str,
    tool: str,
    status: str = "success",
    **result,
) -> None:
    ledger.start(
        ActionDecision.from_tool_call(
            action_id=action_id,
            tool_name=tool,
            arguments={},
        )
    )
    ledger.finish(
        ActionObservation.from_tool_result(
            action_id=action_id,
            tool_name=tool,
            result={"status": status, "summary": f"{tool} {status}", **result},
        )
    )


def test_playwright_mutation_is_typed_and_marks_screen_dirty(monkeypatch) -> None:
    clear_dirty()
    monkeypatch.setattr(
        browser_playwright,
        "_execute_playwright_script",
        lambda script: {
            "ok": True,
            "data": {"selector": "#submit", "clicked": True},
            "error": None,
        },
    )

    result = browser_playwright.playwright_click.__wrapped__("#submit")

    assert result["status"] == "success"
    assert result["error_code"] == ""
    assert result["metadata"]["mutated"] is True
    assert is_dirty() is True


def test_playwright_observation_clears_dirty_screen(monkeypatch) -> None:
    mark_dirty("playwright_click")
    monkeypatch.setattr(
        browser_playwright,
        "_execute_playwright_script",
        lambda script: {
            "ok": True,
            "data": {"selector": "body", "text": "Done"},
            "error": None,
        },
    )

    result = browser_playwright.playwright_get_text.__wrapped__("body")

    assert result["status"] == "success"
    assert result["metadata"]["observed"] is True
    assert is_dirty() is False


@pytest.mark.asyncio
async def test_tool_gateway_blocks_blind_second_gui_mutation() -> None:
    clear_dirty()
    called = False

    def left_click(x: int, y: int) -> dict:
        nonlocal called
        called = True
        return {"status": "success", "summary": "clicked"}

    guarded = gated_tool(left_click)
    mark_dirty("type_text")

    result = await guarded(10, 20)

    assert called is False
    assert result["status"] == "error"
    assert result["error_code"] == "SCREEN_VERIFICATION_REQUIRED"
    assert result["detail"]["retryable"] is True
    clear_dirty()


def test_all_playwright_tools_share_gui_resource_lock() -> None:
    locks = ToolResourceLocks()

    for name in (
        "playwright_navigate",
        "playwright_click",
        "playwright_type",
        "playwright_get_text",
        "playwright_wait_for",
        "playwright_snapshot",
        "playwright_verify",
    ):
        assert locks.resources_for_tool(name) == ("gui",)


def test_completion_rejects_stale_gui_state_then_accepts_verification() -> None:
    ledger = ActionLedger()
    _record(ledger, action_id="1", tool="playwright_click")

    stale = verify_completion(
        request="Click submit",
        final_response="Submitted.",
        ledger=ledger,
    )
    assert stale.verified is False
    assert stale.error_code == "STALE_SCREEN_STATE"

    _record(
        ledger,
        action_id="2",
        tool="playwright_verify",
        verified=True,
        evidence=["Confirmation visible"],
    )
    verified = verify_completion(
        request="Click submit",
        final_response="Submitted.",
        ledger=ledger,
    )
    assert verified.verified is True
    assert verified.status == "completed"


def test_completion_rejects_missing_artifact_and_unresolved_error() -> None:
    missing = verify_completion(
        request="Create a PDF report",
        final_response="The report is complete.",
        ledger=ActionLedger(),
    )
    assert missing.error_code == "MISSING_ARTIFACT"

    ledger = ActionLedger()
    _record(
        ledger,
        action_id="1",
        tool="terminal_worker",
        status="error",
        error_code="COMMAND_FAILED",
        retryable=True,
    )
    failed = verify_completion(
        request="Fix the repository",
        final_response="Done.",
        ledger=ledger,
    )
    assert failed.error_code == "COMMAND_FAILED"
    assert failed.retryable is True


def test_completion_skips_expired_github_push_approval() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        action_id="1",
        tool="github_push",
        status="error",
        error_code="APPROVAL_EXPIRED",
        retryable=False,
    )
    _record(
        ledger,
        action_id="2",
        tool="publish_app_preview",
        status="success",
        artifacts=[{"path": "index.html", "kind": "app_preview"}],
    )
    result = verify_completion(
        request="Create a modern marketing website",
        final_response="The landing page is live in preview.",
        ledger=ledger,
    )
    assert result.verified is True


def test_completion_still_blocks_live_approval_required() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        action_id="1",
        tool="github_push",
        status="approval_required",
        error_code="APPROVAL_REQUIRED",
        retryable=True,
        remaining_work=["Approve the exact blocked github_push action."],
    )
    result = verify_completion(
        request="Create a modern marketing website",
        final_response="The landing page is live in preview.",
        ledger=ledger,
    )
    assert result.verified is False
    assert result.status == "blocked"
    assert result.error_code == "APPROVAL_REQUIRED"


def test_completion_requires_real_final_response() -> None:
    result = verify_completion(
        request="Explain the architecture",
        final_response=None,
        ledger=ActionLedger(),
    )
    assert result.verified is False
    assert result.error_code == "MISSING_FINAL_RESPONSE"


def test_completion_rejects_worker_envelope_as_final_response() -> None:
    from nexus.control_loop import looks_like_worker_envelope

    envelope = (
        '{"status":"success","summary":"Generated PDF report.",'
        '"evidence":["File exists"],"artifacts":[{"path":"outputs/a.pdf","kind":"pdf"}],'
        '"sources":[],"remaining_work":[],"retryable":false,"error_code":""}'
    )
    assert looks_like_worker_envelope(envelope) is True
    assert looks_like_worker_envelope("Here is your report.") is False

    result = verify_completion(
        request="Create a PDF report",
        final_response=envelope,
        ledger=ActionLedger(),
    )
    assert result.verified is False
    assert result.error_code == "MISSING_FINAL_RESPONSE"


def test_completion_ignores_unstructured_prompt_text_for_source_requirements() -> None:
    result = verify_completion(
        request="Research this topic and cite sources.",
        final_response="Hello!",
        ledger=ActionLedger(),
    )

    assert result.verified is True


def test_completion_requires_sources_for_a_structured_deep_research_task() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        action_id="1",
        tool="initialize_task_state",
        metadata={"task_type": "deep_research"},
    )
    ledger = ActionLedger.from_dict(ledger.to_dict())
    result = verify_completion(
        request="hi",
        final_response="It is warm.",
        ledger=ledger,
    )

    assert result.verified is False
    assert result.error_code == "MISSING_SOURCE_EVIDENCE"


def _deep_research_ledger_with_source() -> ActionLedger:
    ledger = ActionLedger()
    _record(
        ledger,
        action_id="1",
        tool="initialize_task_state",
        metadata={"task_type": "deep_research"},
    )
    _record(
        ledger,
        action_id="2",
        tool="web_search",
        results=[{"title": "Rain today", "url": "https://weather.example.com/rain"}],
    )
    # Round-trip through serialization to prove sources survive from_dict.
    return ActionLedger.from_dict(ledger.to_dict())


def test_deep_research_with_sources_but_no_citation_flags_missing_citations() -> None:
    ledger = _deep_research_ledger_with_source()
    assert ledger.all_sources(), "structured sources should be aggregated from web_search"
    result = verify_completion(
        request="research rain",
        final_response="It is warm.",
        ledger=ledger,
    )

    assert result.verified is False
    assert result.error_code == "MISSING_FINAL_CITATIONS"


def test_deep_research_with_sources_and_cited_url_is_verified() -> None:
    ledger = _deep_research_ledger_with_source()
    result = verify_completion(
        request="research rain",
        final_response="It will rain. Source: https://weather.example.com/rain",
        ledger=ledger,
    )

    assert result.verified is True


def test_worker_reported_sources_satisfy_source_evidence() -> None:
    ledger = ActionLedger()
    _record(
        ledger,
        action_id="1",
        tool="initialize_task_state",
        metadata={"task_type": "deep_research"},
    )
    # A worker/subagent surfaces structured sources it gathered internally.
    _record(
        ledger,
        action_id="2",
        tool="terminal_worker",
        sources=[{"title": "Report", "url": "https://example.com/report"}],
    )
    ledger = ActionLedger.from_dict(ledger.to_dict())
    result = verify_completion(
        request="research topic",
        final_response="Findings summarized. See https://example.com/report",
        ledger=ledger,
    )

    assert result.verified is True
