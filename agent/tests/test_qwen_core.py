# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Qwen-only routing, telemetry, and screenshot grounding tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nexus.config import settings
from nexus.model_select import model_candidates
from nexus.qwen_router import _normalize_qwen_request_kwargs
from nexus.runtime_config import SessionRuntimeConfig
from nexus.usage import get_agent_usage_source
from nexus.vision_provider import QwenVisionProvider


@pytest.fixture(autouse=True)
def _set_qwen_provider(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "qwen")


def _runtime(
    *,
    primary: str = "qwen-primary",
    fallbacks: tuple[str, ...] = ("qwen-fallback",),
) -> SessionRuntimeConfig:
    return SessionRuntimeConfig(
        e2b_api_key="",
        gemini_provider="apiKey",
        gemini_api_key="",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model="unused-gemini",
        gemini_agent_fallback_models=(),
        gemini_light_model="unused",
        gemini_live_model="unused",
        gemini_live_region="us-central1",
        gemini_vision_model="unused",
        gemini_vision_fallback_models=(),
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
        qwen_planner_model=primary,
        qwen_planner_fallback_models=fallbacks,
        qwen_worker_model="qwen-worker",
        qwen_visual_model="qwen-visual",
        qwen_micro_model="qwen-micro",
        qwen_vision_model="qwen-vision",
    )


def test_planner_fallbacks_accept_qwen_and_glm_tiers() -> None:
    assert model_candidates("planner", _runtime()) == (
        "qwen-primary",
        "qwen-fallback",
    )


def test_glm_planner_can_fall_back_to_qwen() -> None:
    assert model_candidates(
        "planner",
        _runtime(primary="glm-5.2", fallbacks=("qwen3.6-plus",)),
    ) == ("glm-5.2", "qwen3.6-plus")


def test_unsupported_fallback_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported fallback model"):
        model_candidates(
            "planner",
            _runtime(fallbacks=("deepseek-v4-flash",)),
        )


def test_qwen_thinking_tool_choice_is_normalized() -> None:
    normalized = _normalize_qwen_request_kwargs(
        {"tool_choice": {"type": "function", "function": {"name": "search"}}},
        [{"type": "function"}],
    )
    assert normalized["tool_choice"] == "auto"
    assert _normalize_qwen_request_kwargs({"tool_choice": "none"}, [])["tool_choice"] == "none"


def test_usage_telemetry_reports_qwen_model() -> None:
    assert get_agent_usage_source(_runtime()) == ("agent.qwen", "qwen-primary")


def test_qwen_vision_returns_typed_grounding() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"visible_state":"Login page","focus":"Email",'
                        '"targets":[{"label":"Sign in","kind":"button",'
                        '"coordinates":[120,240],"selector":"button[type=submit]",'
                        '"confidence":0.94}],"visible_text":["Welcome"],'
                        '"errors":[],"next_action":"Click Sign in","confidence":0.9}'
                    )
                )
            )
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = response
    with patch("nexus.vision_provider.OpenAI", return_value=fake_client):
        provider = QwenVisionProvider(
            api_key="test",
            api_base="https://qwen.example/v1",
            primary_model="qwen-vl",
        )
        observation = provider.analyze(
            b"jpeg",
            width=1324,
            height=968,
            task_context="log in",
        )

    assert observation.visible_state == "Login page"
    assert observation.targets[0].x == 120
    assert observation.targets[0].selector == "button[type=submit]"
    assert observation.next_action == "Click Sign in"
    assert observation.model == "qwen-vl"


def test_qwen_vision_clamps_out_of_bounds_coordinates() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"visible_state":"App","targets":[{"label":"Close",'
                        '"coordinates":[9999,-5],"confidence":2}],'
                        '"visible_text":[],"errors":[],"next_action":"Close","confidence":1}'
                    )
                )
            )
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = response
    with patch("nexus.vision_provider.OpenAI", return_value=fake_client):
        observation = QwenVisionProvider(
            api_key="test",
            api_base="https://qwen.example/v1",
            primary_model="qwen-vl",
        ).analyze(b"jpeg", width=100, height=50)
    assert (observation.targets[0].x, observation.targets[0].y) == (100, 0)
    assert observation.targets[0].confidence == 1.0


def test_qwen_vision_emits_fallback_event_before_tier_change() -> None:
    events: list[dict] = []

    def send_json(event: dict) -> None:
        events.append(event)

    good = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"visible_state":"Desktop","targets":[],"visible_text":[],'
                        '"errors":[],"next_action":"Wait","confidence":0.5}'
                    )
                )
            )
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        RuntimeError("rate limited"),
        good,
    ]
    from nexus.tools._context import set_send_json
    from nexus.tracing import TraceContext, set_trace_context

    set_trace_context(TraceContext(trace_id="f" * 32, run_id="run_vision"))
    set_send_json(send_json)
    with patch("nexus.vision_provider.OpenAI", return_value=fake_client):
        observation = QwenVisionProvider(
            api_key="test",
            api_base="https://qwen.example/v1",
            primary_model="qwen-vl-primary",
            fallback_models=("qwen-vl-fallback",),
        ).analyze(b"jpeg", width=100, height=50)
    set_send_json(None)
    assert observation.model == "qwen-vl-fallback"
    assert events
    assert events[0]["type"] == "agent_model_fallback"
    assert events[0]["role"] == "vision"
    assert events[0]["from_model"] == "qwen-vl-primary"
    assert events[0]["to_model"] == "qwen-vl-fallback"
    assert events[0]["trace_id"] == "f" * 32
