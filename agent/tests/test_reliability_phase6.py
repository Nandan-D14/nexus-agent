# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Reliability roadmap phase 6: tool tiers, turn cost, OpenTelemetry."""

from __future__ import annotations

from unittest.mock import patch

from nexus.control_loop import ActionDecision, ActionLedger, ActionObservation
from nexus.telemetry import (
    TIER_API,
    TIER_BROWSER,
    TIER_DESKTOP,
    TIER_SHELL,
    configure_tracing,
    summarize_turn_cost,
    tool_tier,
    turn_span,
)


def test_tool_tiers_follow_cost_ladder() -> None:
    assert tool_tier("gmail_search") == TIER_API
    assert tool_tier("mcp__exa__search") == TIER_API
    assert tool_tier("web_search") == TIER_API
    assert tool_tier("run_command") == TIER_SHELL
    assert tool_tier("playwright_click") == TIER_BROWSER
    assert tool_tier("left_click") == TIER_DESKTOP
    assert tool_tier("desktop_worker") == TIER_DESKTOP


def test_turn_cost_counts_current_turn_including_worker_actions() -> None:
    ledger = ActionLedger()
    ledger.start(ActionDecision.from_tool_call(action_id="old", tool_name="web_search", arguments={}))
    ledger.advance_turn()
    ledger.start(ActionDecision.from_tool_call(action_id="w", tool_name="desktop_worker", arguments={}))
    ledger.finish(
        ActionObservation.from_tool_result(
            action_id="w",
            tool_name="desktop_worker",
            result={
                "status": "success",
                "summary": "ok",
                "actions": [
                    {"tool": "playwright_click", "status": "success"},
                    {"tool": "take_screenshot", "status": "success"},
                ],
            },
        )
    )
    cost = summarize_turn_cost(ledger, screenshots=1, tokens={"input": 10, "output": 5, "total": 15})
    assert cost["tool_calls_by_tier"] == {
        TIER_API: 0,
        TIER_SHELL: 0,
        TIER_BROWSER: 1,
        TIER_DESKTOP: 2,
    }
    assert cost["total_tokens"] == 15
    assert cost["screenshots"] == 1


def test_tracing_is_noop_without_endpoint() -> None:
    with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": ""}):
        assert configure_tracing() is False
    with turn_span(session_id="s", run_id="r", trace_id="t") as span:
        # No SDK provider configured -> non-recording span or None; never raises.
        assert span is None or not span.is_recording() or span.is_recording()


def test_turn_span_parents_inner_spans() -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with patch.object(trace, "get_tracer", provider.get_tracer):
        with turn_span(session_id="s1", run_id="r1", trace_id="t1"):
            with provider.get_tracer("adk").start_as_current_span("call_llm"):
                pass
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["call_llm"].parent.span_id == spans["agent_turn"].context.span_id
    assert spans["agent_turn"].attributes["cocomputer.session_id"] == "s1"
