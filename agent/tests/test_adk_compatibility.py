# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""ADK 2.4 compatibility smoke tests.

These tests deliberately exercise the narrow ADK seams CoComputer depends on.
They should fail loudly when an ADK upgrade changes agent tools, sessions,
events, or the worker-as-tool result contract.
"""

from __future__ import annotations

from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.events import Event
from google.adk.sessions.base_session_service import GetSessionConfig
from google.genai import types

from nexus.agent import create_planner_agent
from nexus.agents.planner_agent import BudgetedAgentTool
from nexus.agents.sub_agents import create_terminal_worker
from nexus.mcp_client import McpRemoteClient, build_mcp_adk_tools
from nexus.session_service import FirestoreSessionService
from nexus.tools._context import reset_worker_call_count
from nexus.ws_handler import _event_to_ws_frame


EXPECTED_ADK_VERSION = "2.4.0"


@pytest.fixture(autouse=True)
def _avoid_live_router_initialization(monkeypatch):
    """Agent construction must not initialize LiteLLM's network-aware router."""
    monkeypatch.setattr(
        "nexus.qwen_router.get_qwen_router",
        lambda: SimpleNamespace(),
    )


def _runtime_config():
    from nexus.runtime_config import SessionRuntimeConfig

    return SessionRuntimeConfig(
        e2b_api_key="test-e2b",
        gemini_provider="apiKey",
        gemini_api_key="test-gemini",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model="gemini-test",
        gemini_agent_fallback_models=(),
        gemini_light_model="gemini-light-test",
        gemini_live_model="gemini-live-test",
        gemini_live_region="us-central1",
        gemini_vision_model="gemini-vision-test",
        gemini_vision_fallback_models=(),
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
    )


def test_google_adk_version_is_pinned() -> None:
    assert version("google-adk") == EXPECTED_ADK_VERSION


def test_planner_tool_declarations_survive_adk_upgrade() -> None:
    planner = create_planner_agent(_runtime_config())
    names = {
        str(getattr(tool, "name", getattr(tool, "__name__", "")))
        for tool in planner.tools
    }

    assert {"terminal_worker", "desktop_worker", "ask_user", "web_search"} <= names
    assert "run_command" not in names
    assert "take_screenshot" not in names
    worker_tools = [
        tool for tool in planner.tools if getattr(tool, "name", "") in {"terminal_worker", "desktop_worker"}
    ]
    assert all(isinstance(tool, BudgetedAgentTool) for tool in worker_tools)
    assert all(tool.skip_summarization is True for tool in worker_tools)


@pytest.mark.asyncio
async def test_agent_tool_skip_summarization_returns_worker_text() -> None:
    worker = create_terminal_worker(_runtime_config())
    tool = BudgetedAgentTool(agent=worker, skip_summarization=True)
    reset_worker_call_count()

    class _SessionService:
        async def create_session(self, **kwargs):
            return SimpleNamespace(user_id=kwargs["user_id"], id="worker-session")

    class _Runner:
        def __init__(self, **kwargs) -> None:
            self.session_service = _SessionService()
            self.plugin_manager = SimpleNamespace(
                set_skip_closing_plugins=lambda enabled: None
            )

        async def run_async(self, **kwargs):
            yield SimpleNamespace(
                actions=SimpleNamespace(state_delta={}),
                content=types.Content(
                    role="model",
                           parts=[
                               types.Part(
                                   text=(
                                       '{"status":"success","summary":"worker complete",'
                                       '"evidence":["worker evidence returned"],'
                                       '"artifacts":[],"remaining_work":[],"retryable":false}'
                                   )
                               )
                           ],
                ),
                grounding_metadata=None,
            )

        async def close(self) -> None:
            return None

    tool_context = SimpleNamespace(
        actions=SimpleNamespace(skip_summarization=False),
        state=SimpleNamespace(to_dict=lambda: {}),
        _invocation_context=SimpleNamespace(
            app_name="nexus",
            user_id="user-1",
            credential_service=None,
            plugin_manager=SimpleNamespace(plugins=[]),
        ),
    )

    with patch("google.adk.runners.Runner", _Runner):
        result = await tool.run_async(
            args={"request": "return worker evidence"},
            tool_context=tool_context,
        )

    assert result["status"] == "success"
    assert result["evidence"] == ["worker evidence returned"]
    assert tool_context.actions.skip_summarization is True


class _Snapshot:
    def __init__(self, data: dict | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict:
        return dict(self._data or {})


class _EventCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def document(self, key: str):
        collection = self

        class _EventDoc:
            def set(self, data: dict) -> None:
                collection.docs[key] = dict(data)

        return _EventDoc()

    def order_by(self, field: str):
        assert field == "timestamp"
        return self

    def stream(self):
        return [
            _Snapshot(data)
            for data in sorted(self.docs.values(), key=lambda item: item.get("timestamp", 0))
        ]


class _SessionDoc:
    def __init__(self) -> None:
        self.data: dict | None = None
        self.events = _EventCollection()

    def set(self, data: dict, merge: bool = False) -> None:
        if merge and self.data:
            self.data.update(data)
        else:
            self.data = dict(data)

    def get(self) -> _Snapshot:
        return _Snapshot(self.data)

    def delete(self) -> None:
        self.data = None

    def collection(self, name: str) -> _EventCollection:
        assert name == "events"
        return self.events


class _SessionCollection:
    def __init__(self) -> None:
        self.docs: dict[str, _SessionDoc] = {}

    def document(self, key: str) -> _SessionDoc:
        return self.docs.setdefault(key, _SessionDoc())


class _Firestore:
    def __init__(self) -> None:
        self.sessions = _SessionCollection()

    def collection(self, name: str) -> _SessionCollection:
        assert name == "adk_sessions"
        return self.sessions


@pytest.mark.asyncio
async def test_firestore_session_service_replays_adk_events() -> None:
    service = FirestoreSessionService.__new__(FirestoreSessionService)
    service._db = _Firestore()

    session = await service.create_session(
        app_name="nexus",
        user_id="user-1",
        session_id="session-1",
        state={"goal": "test replay"},
    )
    event = Event(
        author="user",
        invocation_id="invocation-1",
        content=types.Content(role="user", parts=[types.Part(text="hello")]),
    )
    await service.append_event(session, event)

    replayed = await service.get_session(
        app_name="nexus",
        user_id="user-1",
        session_id="session-1",
        config=GetSessionConfig(num_recent_events=10),
    )

    assert replayed is not None
    assert replayed.state["goal"] == "test replay"
    assert len(replayed.events) == 1
    assert replayed.events[0].content.parts[0].text == "hello"


@pytest.mark.parametrize(
    ("event_type", "payload", "required_key"),
    [
        ("agent_tool_call", {"tool": "run_command", "args": {}}, "tool"),
        ("agent_tool_result", {"tool": "run_command", "output": "ok"}, "output"),
        ("agent_complete", {"summary": "done"}, "summary"),
        ("error", {"code": "AGENT_ERROR", "message": "failed"}, "code"),
    ],
)
def test_durable_events_replay_as_websocket_contract(
    event_type: str,
    payload: dict,
    required_key: str,
) -> None:
    frame = _event_to_ws_frame(
        SimpleNamespace(
            event_type=event_type,
            payload=payload,
            event_id="evt-1",
            task_id="task-1",
            run_id="run-1",
            seq=7,
        )
    )

    assert frame["type"] == event_type
    assert frame[required_key] == payload[required_key]
    assert frame["event_id"] == "evt-1"
    assert frame["task_id"] == "task-1"
    assert frame["run_id"] == "run-1"
    assert frame["seq"] == 7


def _connection(tool_name: str = "lookup"):
    return SimpleNamespace(
        connector_type="mcp_remote_http",
        connection_id="conn-1",
        name="Test MCP",
        private={
            "url": "https://mcp.example.test",
            "bearerToken": "",
            "tools": [{"name": tool_name, "description": "Lookup data"}],
        },
    )


@pytest.mark.asyncio
async def test_remote_mcp_adk_tool_returns_normalized_result(monkeypatch) -> None:
    call_tool = AsyncMock(
        return_value={
            "status": "success",
            "text": "MCP evidence",
            "content": [],
            "structured": {"ok": True},
            "latency_ms": 12,
            "tool": "lookup",
        }
    )
    monkeypatch.setattr(McpRemoteClient, "call_tool", call_tool)
    tool = build_mcp_adk_tools([_connection()])[0]

    result = await tool(arguments={"query": "safe"})

    assert result["status"] == "success"
    assert result["text"] == "MCP evidence"
    assert result["connection_id"] == "conn-1"
    call_tool.assert_awaited_once_with(tool_name="lookup", arguments={"query": "safe"})


@pytest.mark.asyncio
async def test_remote_mcp_adk_tool_converts_transport_error(monkeypatch) -> None:
    monkeypatch.setattr(
        McpRemoteClient,
        "call_tool",
        AsyncMock(side_effect=RuntimeError("transport unavailable")),
    )
    tool = build_mcp_adk_tools([_connection()])[0]

    result = await tool(arguments={"query": "safe"})

    assert result["status"] == "error"
    assert "transport unavailable" in result["error"]
    assert result["tool"] == "lookup"
