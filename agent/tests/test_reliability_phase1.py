# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Reliability roadmap phase 1: screen state, SSRF, fallbacks, caps, untrusted scope."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from nexus.tools import screen_state
from nexus.tools._context import (
    clear_untrusted_content,
    mark_untrusted_content_seen,
    set_session_id,
    untrusted_content_in_scope,
)
from nexus.tools.verification import should_verify_before_action


def test_screen_dirty_flag_survives_to_thread_boundary() -> None:
    async def scenario() -> None:
        set_session_id("sess-a")
        screen_state.clear_dirty()
        # Sync GUI tools run in a pool thread via normalized_tool.
        await asyncio.to_thread(screen_state.mark_dirty, "left_click")
        assert screen_state.is_dirty()
        assert should_verify_before_action("left_click") is not None

    asyncio.run(scenario())
    screen_state.clear_session_state("sess-a")


def test_screen_state_is_isolated_per_session() -> None:
    async def mark(session_id: str) -> None:
        set_session_id(session_id)
        await asyncio.to_thread(screen_state.mark_dirty, "type_text")

    async def check(session_id: str) -> bool:
        set_session_id(session_id)
        return screen_state.is_dirty()

    asyncio.run(mark("sess-dirty"))
    assert asyncio.run(check("sess-dirty")) is True
    assert asyncio.run(check("sess-clean")) is False
    screen_state.clear_session_state("sess-dirty")
    assert asyncio.run(check("sess-dirty")) is False


def test_gui_tool_lists_share_one_registry() -> None:
    from nexus.control_loop import GUI_MUTATIONS
    from nexus.subagent_resources import GUI_TOOLS

    assert GUI_MUTATIONS <= GUI_TOOLS
    assert "triple_click" in GUI_TOOLS
    assert "move_mouse" in GUI_TOOLS


def test_untrusted_scope_propagates_from_child_task() -> None:
    async def tool_in_child_task() -> None:
        mark_untrusted_content_seen()

    async def scenario() -> tuple[bool, bool]:
        clear_untrusted_content()
        await asyncio.create_task(tool_in_child_task())
        seen = untrusted_content_in_scope()
        clear_untrusted_content()
        return seen, untrusted_content_in_scope()

    seen, after_reset = asyncio.run(scenario())
    assert seen is True
    assert after_reset is False


def _mock_client_factory(handler):
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    return factory


def test_scrape_blocks_metadata_address() -> None:
    from nexus.tools.web import scrape_web_page

    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(200, text="secret")

    with patch("nexus.tools.web.httpx.AsyncClient", side_effect=_mock_client_factory(handler)):
        result = asyncio.run(scrape_web_page("http://169.254.169.254/latest/meta-data/"))

    assert result["status"] == "error"
    assert result["error_code"] == "UNSAFE_URL"
    assert hits == []


def test_scrape_blocks_redirect_to_metadata_address() -> None:
    from nexus.tools.web import scrape_web_page

    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    # The first hop is a public literal IP so no DNS is needed in tests.
    with patch("nexus.tools.web.httpx.AsyncClient", side_effect=_mock_client_factory(handler)):
        result = asyncio.run(scrape_web_page("http://93.184.216.34/start"))

    assert result["status"] == "error"
    assert result["error_code"] == "UNSAFE_URL"
    assert hits == ["http://93.184.216.34/start"]


def test_default_roles_have_distinct_fallbacks() -> None:
    from nexus.bynara_router import _configured_bynara_fallbacks
    from nexus.config import model_roles_without_fallback, settings

    with (
        patch.object(settings, "planner_model", "primary-x"),
        patch.object(settings, "planner_fallback_models", "primary-x,backup-y"),
        patch.object(settings, "worker_model", "primary-x"),
        patch.object(settings, "worker_fallback_models", "backup-z"),
        patch.object(settings, "worker_visual_model", "vis"),
        patch.object(settings, "worker_visual_fallback_models", "vis"),
        patch.object(settings, "micro_model", "primary-x"),
        patch.object(settings, "micro_fallback_models", ""),
    ):
        assert [role for role, *_ in model_roles_without_fallback()] == [
            "worker_visual",
            "micro",
        ]
        assert _configured_bynara_fallbacks() == [{"primary-x": ["backup-y", "backup-z"]}]


def test_shipped_defaults_have_fallbacks() -> None:
    from nexus.config import Settings

    defaults = Settings.model_fields
    for role in ("planner", "worker", "worker_visual", "micro"):
        primary = defaults[f"{role}_model"].default
        fallbacks = [
            m.strip()
            for m in defaults[f"{role}_fallback_models"].default.split(",")
            if m.strip()
        ]
        assert any(m != primary for m in fallbacks), role


def test_subagent_spawn_respects_concurrency_cap() -> None:
    from nexus.config import settings
    from nexus.subagent_store import SubagentLimitError
    from nexus.subagents import SubagentSupervisor

    supervisor = object.__new__(SubagentSupervisor)
    supervisor.__dict__["_records"] = {
        f"sub_{i}": SimpleNamespace(status="running") for i in range(2)
    }

    with patch.object(settings, "subagent_max_concurrent", 2):
        with pytest.raises(SubagentLimitError):
            asyncio.run(supervisor.spawn(prompt="x", role="worker", type_name="general"))

    supervisor.__dict__["_records"]["sub_0"].status = "completed"
    assert supervisor.active_count() == 1
