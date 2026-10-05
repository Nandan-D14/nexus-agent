# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""OpenTelemetry export and per-turn cost/tier metrics.

ADK already emits OTel spans for every model call and tool execution. This
module (a) installs an OTLP exporter when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is
set and the optional exporter package is installed — Langfuse, Honeycomb,
Grafana Tempo, and Cloud Trace collectors all accept OTLP — and (b) wraps each
agent turn in a parent span so ADK's spans nest under one trace per turn,
annotated with the turn's cost and tool-tier mix.

Everything is a no-op without an endpoint; tracing never breaks a turn.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_TRACER_NAME = "cocomputer.nexus"
_configured = False

# Cost ladder: prefer the cheapest surface that can do the job.
TIER_API = "api"          # native connectors, MCP, web search/fetch
TIER_SHELL = "shell"      # sandbox terminal / files / document generation
TIER_BROWSER = "browser"  # Playwright DOM automation
TIER_DESKTOP = "desktop"  # pixel-level GUI control + vision screenshots
_DESKTOP_TOOLS = frozenset({
    "take_screenshot", "move_mouse", "left_click", "right_click", "double_click",
    "triple_click", "type_text", "press_key", "scroll_screen", "drag", "open_browser",
})
_SHELL_TOOLS = frozenset({
    "run_command", "terminal_worker", "write_workspace_file", "read_workspace_file",
    "list_workspace_files", "extract_pdf_text", "extract_document_text",
    "generate_pdf_report", "generate_excel_report", "generate_docx_report",
    "generate_pptx_report", "save_as_artifact", "publish_app_preview",
    "scaffold_web_project", "prepare_task_workspace",
})


def tool_tier(tool_name: str) -> str:
    """Return the cost tier for a tool name."""
    name = str(tool_name or "")
    if name in _DESKTOP_TOOLS or name == "desktop_worker":
        return TIER_DESKTOP
    if name.startswith("playwright_"):
        return TIER_BROWSER
    if name in _SHELL_TOOLS:
        return TIER_SHELL
    return TIER_API


def configure_tracing() -> bool:
    """Install an OTLP span exporter if configured. Safe to call repeatedly."""
    global _configured
    if _configured:
        return True
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry-exporter-otlp-proto-http "
            "is not installed; tracing export disabled"
        )
        return False
    service = os.environ.get("OTEL_SERVICE_NAME", "cocomputer-agent")
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    # Endpoint, headers (e.g. Langfuse basic auth) come from the standard
    # OTEL_EXPORTER_OTLP_* environment variables.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True
    logger.info("OpenTelemetry OTLP export enabled (service=%s)", service)
    return True


@contextlib.contextmanager
def turn_span(*, session_id: str, run_id: str, trace_id: str) -> Iterator[Any]:
    """Parent span for one agent turn (yields ``None`` when tracing is unavailable)."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return
    tracer = trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span("agent_turn") as span:
        try:
            span.set_attribute("cocomputer.session_id", session_id or "")
            span.set_attribute("cocomputer.run_id", run_id or "")
            span.set_attribute("cocomputer.trace_id", trace_id or "")
        except Exception:
            pass
        yield span


def summarize_turn_cost(ledger: Any, *, screenshots: int, tokens: dict[str, int]) -> dict[str, Any]:
    """Compact per-turn cost record: tokens, screenshots, and tool calls per tier."""
    tiers = {TIER_API: 0, TIER_SHELL: 0, TIER_BROWSER: 0, TIER_DESKTOP: 0}
    current = getattr(ledger, "current_turn_index", None)
    for record in getattr(ledger, "records", None) or []:
        if current is not None and getattr(record, "turn_index", current) != current:
            continue
        action = getattr(getattr(record, "decision", None), "action", "")
        tiers[tool_tier(action)] += 1
    return {
        "input_tokens": int(tokens.get("input", 0)),
        "output_tokens": int(tokens.get("output", 0)),
        "total_tokens": int(tokens.get("total", 0)),
        "screenshots": int(screenshots),
        "tool_calls_by_tier": tiers,
    }


def annotate_turn(span: Any, result: Any, cost: dict[str, Any]) -> None:
    if span is None:
        return
    try:
        status = result.get("status") if isinstance(result, dict) else ""
        span.set_attribute("cocomputer.status", str(status or ""))
        for key in ("input_tokens", "output_tokens", "total_tokens", "screenshots"):
            span.set_attribute(f"cocomputer.{key}", int(cost.get(key, 0)))
        for tier, count in (cost.get("tool_calls_by_tier") or {}).items():
            span.set_attribute(f"cocomputer.tools.{tier}", int(count))
    except Exception:
        logger.debug("Could not annotate turn span", exc_info=True)


__all__ = [
    "annotate_turn",
    "configure_tracing",
    "summarize_turn_cost",
    "tool_tier",
    "turn_span",
]
