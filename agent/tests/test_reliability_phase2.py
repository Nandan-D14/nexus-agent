# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Reliability roadmap phase 2: condenser, recitation, budgets, observation cap."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from google.genai import types

from nexus import context_condenser
from nexus.config import settings
from nexus.context_condenser import (
    CONDENSED_PREFIX,
    clear_condensed_cache,
    make_context_condenser,
    make_todo_reciter,
)
from nexus.context_window import _input_token_budget


def _text(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


def _request(contents):
    return SimpleNamespace(contents=list(contents), config=SimpleNamespace(system_instruction=None))


def _ctx(session: str = "sess-c", agent: str = "nexus_planner"):
    invocation = SimpleNamespace(session=SimpleNamespace(id=session))
    return SimpleNamespace(_invocation_context=invocation, agent_name=agent, state={})


def _history(n: int, size: int = 2000) -> list[types.Content]:
    contents = [_text("user", "GOAL build a sales dashboard " + "g" * size)]
    for i in range(1, n):
        contents.append(_text("model" if i % 2 else "user", f"STEP{i} " + "x" * size))
    return contents


class _Budget:
    def __enter__(self):
        self._patches = [
            patch.object(settings, "enforce_context_budget", True),
            patch.object(settings, "context_condenser_enabled", True),
            patch.object(settings, "model_context_limit", 10_000),
            patch.object(settings, "context_input_budget_ratio", 1.0),
            patch.object(settings, "context_working_budget_tokens", 0),
            patch.object(settings, "context_condense_trigger_ratio", 0.8),
            patch.object(settings, "context_condense_keep_ratio", 0.4),
        ]
        for p in self._patches:
            p.start()
        clear_condensed_cache()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        clear_condensed_cache()


def test_condenser_replaces_old_history_with_summary() -> None:
    with _Budget():
        summarize = AsyncMock(return_value="GOAL: sales dashboard\nOPEN: chart")
        req = _request(_history(30))  # ~15k tokens > 8k trigger
        ctx = _ctx()
        with patch.object(context_condenser, "_summarize", summarize):
            asyncio.run(make_context_condenser()(ctx, req))

        assert summarize.await_count == 1
        first = req.contents[0].parts[0].text
        assert first.startswith(CONDENSED_PREFIX)
        assert "sales dashboard" in first
        assert req.contents[-1].parts[0].text.startswith("STEP29")
        assert len(req.contents) < 30
        # Persisted for restart recovery.
        assert "nexus_planner" in ctx.state["nexus_condensed_context"]


def test_condenser_reuses_cached_summary_without_new_call() -> None:
    with _Budget():
        summarize = AsyncMock(return_value="SUMMARY-1")
        history = _history(30)
        with patch.object(context_condenser, "_summarize", summarize):
            asyncio.run(make_context_condenser()(_ctx(), _request(history)))
            # One more small step: still under trigger in the condensed view.
            req = _request([*history, _text("model", "small step")])
            asyncio.run(make_context_condenser()(_ctx(), req))

        assert summarize.await_count == 1
        assert req.contents[0].parts[0].text == CONDENSED_PREFIX + "SUMMARY-1"
        assert req.contents[-1].parts[0].text == "small step"


def test_condenser_failure_leaves_contents_for_trimmer() -> None:
    with _Budget():
        failing = AsyncMock(side_effect=RuntimeError("model down"))
        history = _history(30)
        req = _request(history)
        with patch.object(context_condenser, "_summarize", failing):
            asyncio.run(make_context_condenser()(_ctx(), req))
        assert req.contents == history


def test_condenser_noop_under_trigger() -> None:
    with _Budget():
        summarize = AsyncMock(return_value="unused")
        history = _history(6, size=200)
        req = _request(history)
        with patch.object(context_condenser, "_summarize", summarize):
            asyncio.run(make_context_condenser()(_ctx(), req))
        assert summarize.await_count == 0
        assert req.contents == history


def test_condenser_keeps_tool_call_with_its_response() -> None:
    with _Budget():
        history = _history(28)
        call = types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(id="c1", name="run_command", args={"c": "x" * 4000}))],
        )
        response = types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(id="c1", name="run_command", response={"o": "y" * 4000}))],
        )
        req = _request([*history, call, response])
        with patch.object(context_condenser, "_summarize", AsyncMock(return_value="S")):
            asyncio.run(make_context_condenser()(_ctx(), req))
        kept = req.contents[1:]
        for index, content in enumerate(kept):
            if any(getattr(p, "function_response", None) for p in content.parts):
                assert index > 0 and any(getattr(p, "function_call", None) for p in kept[index - 1].parts)


def test_todo_reciter_appends_open_items_mid_loop() -> None:
    items = [
        {"title": "Collect data", "status": "done", "note": ""},
        {"title": "Build chart", "status": "in_progress", "note": ""},
        {"title": "Publish", "status": "pending", "note": ""},
    ]
    tool_turn = types.Content(
        role="user",
        parts=[types.Part(function_response=types.FunctionResponse(name="run_command", response={"ok": 1}))],
    )
    req = _request([_text("user", "go"), tool_turn])
    with patch.object(context_condenser, "_todo_items", return_value=items):
        make_todo_reciter()(None, req)
    reminder = req.contents[-1].parts[0].text
    assert "[x] Collect data" in reminder
    assert "[~] Build chart" in reminder
    assert "[ ] Publish" in reminder

    # Not on a fresh user message.
    fresh = _request([_text("user", "new task")])
    with patch.object(context_condenser, "_todo_items", return_value=items):
        make_todo_reciter()(None, fresh)
    assert len(fresh.contents) == 1


def test_todo_cache_tracks_emitted_items() -> None:
    from nexus.tools._context import set_session_id
    from nexus.tools.workspace import _emit_todo_update, get_cached_todo_items

    async def scenario():
        set_session_id("sess-todo")
        await _emit_todo_update([{"title": "A", "status": "pending", "note": ""}])
        return get_cached_todo_items()

    assert asyncio.run(scenario()) == [{"title": "A", "status": "pending", "note": ""}]


def test_working_budget_caps_large_context_models() -> None:
    with (
        patch.object(settings, "model_context_limit", 1_000_000),
        patch.object(settings, "context_input_budget_ratio", 0.85),
        patch.object(settings, "context_working_budget_tokens", 160_000),
    ):
        _, budget = _input_token_budget(None)
    assert budget == 160_000


def test_tool_schemas_not_evicted_by_long_history() -> None:
    from nexus.context_window import make_context_trimmer

    mcp = types.FunctionDeclaration(name="mcp__exa__search", description="search " * 50)
    with (
        patch.object(settings, "enforce_context_budget", True),
        patch.object(settings, "model_context_limit", 4_000),
        patch.object(settings, "context_input_budget_ratio", 1.0),
        patch.object(settings, "context_working_budget_tokens", 0),
    ):
        req = _request(_history(12, size=1500))
        req.config.tools = [types.Tool(function_declarations=[mcp])]
        make_context_trimmer()(None, req)
    names = [d.name for t in req.config.tools for d in t.function_declarations]
    assert names == ["mcp__exa__search"]


def test_observation_cap_clips_longest_strings_only() -> None:
    from nexus.tools.base import _normalize

    with patch.object(settings, "tool_observation_max_chars", 5_000):
        result = _normalize(
            "read_x",
            {"status": "success", "summary": "ok", "metadata": {"path": "/a/b.txt", "content": "z" * 50_000}},
        )
    import json

    assert len(json.dumps(result)) < 6_500
    assert result["metadata"]["path"] == "/a/b.txt"
    assert "chars truncated" in result["metadata"]["content"]
    assert result["metadata"]["observation_truncated"] is True


def test_observation_cap_leaves_small_results_untouched() -> None:
    from nexus.tools.base import _normalize

    raw = {"status": "success", "summary": "ok", "metadata": {"n": 1}}
    result = _normalize("t", raw)
    assert result["metadata"] == {"n": 1}
