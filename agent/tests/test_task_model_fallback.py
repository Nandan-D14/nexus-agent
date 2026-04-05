from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.agent import AgentTurnResult
from nexus import orchestrator as orchestrator_module
from nexus.runtime_config import SessionRuntimeConfig
from nexus.tools._context import get_runtime_config


def _runtime_config(
    *,
    provider: str,
    primary: str,
    fallbacks: tuple[str, ...] = (),
) -> SessionRuntimeConfig:
    return SessionRuntimeConfig(
        e2b_api_key="test-e2b",
        gemini_provider=provider,  # type: ignore[arg-type]
        gemini_api_key="",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model=primary,
        gemini_agent_fallback_models=fallbacks,
        gemini_light_model="light-model",
        gemini_live_model="live-model",
        gemini_live_region="us-central1",
        gemini_vision_model="vision-model",
        gemini_vision_fallback_models=("vision-fallback",),
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
    )


def _session(runtime_config: SessionRuntimeConfig):
    return SimpleNamespace(
        id="session-123",
        owner_id="user-123",
        runtime_config=runtime_config,
        current_run_id=None,
        seed_context="",
        stream_url="",
        run_status="queued",
        artifact_count=0,
        sandbox=MagicMock(),
    )


class TaskModelFallbackTests(IsolatedAsyncioTestCase):
    async def test_api_key_session_switches_to_fallback_model(self) -> None:
        config = _runtime_config(
            provider="apiKey",
            primary="gemini-3.1-pro-preview",
            fallbacks=("gemini-3-flash-preview", "gemini-2.5-flash"),
        )
        session = _session(config)
        ws = SimpleNamespace(send_json=AsyncMock())

        created_models: list[str] = []
        reused_session_services: list[object | None] = []
        run_calls: list[str] = []
        first_session_service = object()
        first_runner = object()
        second_runner = object()

        def fake_create_multi_agent(runtime_config, task_model_override=None):
            created_models.append(runtime_config.gemini_agent_model)
            return MagicMock(name=f"agent-{runtime_config.gemini_agent_model}")

        def fake_create_runner(agent, session_service=None):
            reused_session_services.append(session_service)
            if session_service is None:
                return first_runner, first_session_service
            return second_runner, session_service

        async def fake_run_agent_turn(**kwargs):
            run_calls.append(kwargs["runtime_config"].gemini_agent_model)
            if len(run_calls) == 1:
                raise RuntimeError("429 daily limit exceeded")
            return AgentTurnResult(response="ok", usage_records=[])

        with (
            patch.object(orchestrator_module, "create_multi_agent", side_effect=fake_create_multi_agent),
            patch.object(orchestrator_module, "create_runner", side_effect=fake_create_runner),
            patch.object(orchestrator_module, "run_agent_turn", side_effect=fake_run_agent_turn),
        ):
            orchestrator = orchestrator_module.NexusOrchestrator(session=session, ws=ws)
            orchestrator._RATE_LIMIT_MAX_RETRIES = 1
            orchestrator._RATE_LIMIT_BASE_WAIT = 0
            orchestrator._adk_session_id = "adk-session"
            result = await orchestrator._run_agent_with_retry("inspect the repo")

        self.assertEqual(result.response, "ok")
        self.assertEqual(
            run_calls,
            ["gemini-3.1-pro-preview", "gemini-3-flash-preview"],
        )
        self.assertEqual(
            created_models,
            ["gemini-3.1-pro-preview", "gemini-3-flash-preview"],
        )
        self.assertEqual(reused_session_services, [None, first_session_service])
        self.assertEqual(orchestrator.runtime_config.gemini_agent_model, "gemini-3-flash-preview")
        self.assertEqual(session.runtime_config.gemini_agent_model, "gemini-3-flash-preview")
        self.assertEqual(get_runtime_config().gemini_agent_model, "gemini-3-flash-preview")
        self.assertTrue(ws.send_json.await_count >= 1)

    async def test_vertex_session_uses_fallback_chain_when_configured(self) -> None:
        config = _runtime_config(
            provider="vertex",
            primary="vertex-default-model",
            fallbacks=("vertex-fallback-model",),
        )
        session = _session(config)
        ws = SimpleNamespace(send_json=AsyncMock())

        created_models: list[str] = []
        run_calls: list[str] = []
        first_session_service = object()
        first_runner = object()
        second_runner = object()

        def fake_create_multi_agent(runtime_config, task_model_override=None):
            created_models.append(runtime_config.gemini_agent_model)
            return MagicMock(name=f"agent-{runtime_config.gemini_agent_model}")

        def fake_create_runner(agent, session_service=None):
            if session_service is None:
                return first_runner, first_session_service
            return second_runner, session_service

        async def fake_run_agent_turn(**kwargs):
            run_calls.append(kwargs["runtime_config"].gemini_agent_model)
            if len(run_calls) == 1:
                raise RuntimeError("429 quota exceeded")
            return AgentTurnResult(response="ok", usage_records=[])

        with (
            patch.object(orchestrator_module, "create_multi_agent", side_effect=fake_create_multi_agent),
            patch.object(orchestrator_module, "create_runner", side_effect=fake_create_runner),
            patch.object(orchestrator_module, "run_agent_turn", side_effect=fake_run_agent_turn),
        ):
            orchestrator = orchestrator_module.NexusOrchestrator(session=session, ws=ws)
            orchestrator._RATE_LIMIT_MAX_RETRIES = 1
            orchestrator._RATE_LIMIT_BASE_WAIT = 0
            orchestrator._adk_session_id = "adk-session"
            result = await orchestrator._run_agent_with_retry("run the task")

        self.assertEqual(result.response, "ok")
        self.assertEqual(run_calls, ["vertex-default-model", "vertex-fallback-model"])
        self.assertEqual(created_models, ["vertex-default-model", "vertex-fallback-model"])

    async def test_unexpected_exception_returns_error_result(self) -> None:
        config = _runtime_config(
            provider="apiKey",
            primary="gemini-3.1-pro-preview",
            fallbacks=("gemini-3-flash-preview",),
        )
        session = _session(config)
        ws = SimpleNamespace(send_json=AsyncMock())

        async def fake_run_agent_turn(**kwargs):
            raise ValueError("item_index must be at least 1")

        with (
            patch.object(orchestrator_module, "run_agent_turn", side_effect=fake_run_agent_turn),
        ):
            orchestrator = orchestrator_module.NexusOrchestrator(session=session, ws=ws)
            orchestrator._adk_session_id = "adk-session"
            result = await orchestrator._run_agent_with_retry("run the task")

        self.assertIsNone(result.response)
        self.assertEqual(result.usage_records, [])
        self.assertEqual(result.error, "item_index must be at least 1")


class WebsocketSendLockTests(IsolatedAsyncioTestCase):
    async def test_send_json_serializes_concurrent_writes(self) -> None:
        class ConcurrentUnsafeWebSocket:
            def __init__(self) -> None:
                self.in_flight = 0
                self.sent: list[dict[str, str]] = []

            async def send_json(self, data: dict[str, str]) -> None:
                self.in_flight += 1
                if self.in_flight > 1:
                    self.in_flight -= 1
                    raise RuntimeError("concurrent send")
                await asyncio.sleep(0.01)
                self.sent.append(data)
                self.in_flight -= 1

        orchestrator = orchestrator_module.NexusOrchestrator.__new__(orchestrator_module.NexusOrchestrator)
        orchestrator.ws = ConcurrentUnsafeWebSocket()
        orchestrator._ws_send_lock = asyncio.Lock()

        await asyncio.gather(
            orchestrator._send_json({"type": "step_started"}),
            orchestrator._send_json({"type": "agent_tool_call"}),
        )

        self.assertEqual(
            [item["type"] for item in orchestrator.ws.sent],
            ["step_started", "agent_tool_call"],
        )
