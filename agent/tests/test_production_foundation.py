# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.config import settings
from nexus.policy import evaluate_tool_policy
from nexus.production_tasks import (
    DurableTask,
    DurableTaskEvent,
    DurableTaskRun,
    build_execution_payload,
    canonicalize_task_status,
    history_event_projection_from_durable,
    history_run_projection_from_durable,
    history_task_projection_from_durable,
    map_durable_status_to_history,
    map_history_status_to_durable,
)
from nexus.routers import sessions as sessions_router
from nexus import sandbox as sandbox_module
from nexus import task_worker as task_worker_module
from nexus import storage
from nexus.routers.worker import _validate_worker_token
from nexus.sandbox import SandboxLifecycleController
from nexus.storage import artifact_blob_name, artifact_storage_metadata
from nexus.task_queue import TaskQueue
from nexus.task_worker import TaskWorker, WorkerRunResult


def test_auto_mode_allows_low_risk_local_tool() -> None:
    decision = evaluate_tool_policy(
        "read_workspace_file",
        {"relative_path": "notes.md"},
        autonomy_mode="auto",
    )

    assert decision.action == "allow"
    assert decision.risk == "low"


def test_auto_mode_still_requires_approval_for_external_side_effect() -> None:
    decision = evaluate_tool_policy(
        "gmail_send",
        {"to": "user@example.com", "body": "hello"},
        autonomy_mode="auto",
    )

    assert decision.action == "require_approval"
    assert decision.risk == "high"


def test_policy_denies_secret_exfiltration_command() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "cat ~/.config/rclone/rclone.conf"},
        autonomy_mode="auto",
    )

    assert decision.action == "deny"
    assert decision.risk == "blocked"


def test_durable_status_mapping_is_canonical() -> None:
    assert canonicalize_task_status("ACTIVE") == "running"
    assert canonicalize_task_status("ended") == "completed"
    assert canonicalize_task_status("destroyed") == "cancelled"
    assert map_history_status_to_durable("error") == "failed"
    assert map_durable_status_to_history("waiting_approval") == "running"
    assert map_durable_status_to_history("paused") == "queued"


def test_history_projection_helpers_from_durable_state() -> None:
    now = datetime.now(timezone.utc)
    task = DurableTask(
        task_id="task_1",
        owner_id="user_1",
        title="Do work",
        status="waiting_approval",
        created_at=now,
        updated_at=now,
        session_id="session_1",
        current_run_id="run_1",
    )
    task_projection = history_task_projection_from_durable(task)
    assert task_projection["taskId"] == "task_1"
    assert task_projection["status"] == "running"
    assert task_projection["canonicalSource"] == "production_tasks"

    event = DurableTaskEvent(
        event_id="evt_1",
        task_id="task_1",
        owner_id="user_1",
        event_type="agent_complete",
        created_at=now,
        payload={"summary": "done"},
        run_id="run_1",
        seq=3,
    )
    event_projection = history_event_projection_from_durable(event)
    assert event_projection["runStatus"] == "completed"
    assert event_projection["summary"] == "done"
    assert event_projection["lastEventSeq"] == 3

    run = DurableTaskRun(
        run_id="run_1",
        task_id="task_1",
        owner_id="user_1",
        status="completed",
        created_at=now,
        updated_at=now,
        session_id="session_1",
        execution_payload={"input_text": "do work"},
    )
    run_projection = history_run_projection_from_durable(run)
    assert run_projection["status"] == "completed"
    assert run_projection["executionPayload"] == {"input_text": "do work"}


def test_build_execution_payload_is_canonical_and_sanitized() -> None:
    payload = build_execution_payload(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        session_id="session_1",
        input_text="do work",
        connector_ids=[" github ", "", "drive"],
        uploaded_files=[{"name": "a.txt"}, "bad"],  # type: ignore[list-item]
        runtime_config_snapshot={"gemini_provider": "apiKey"},
        autonomy_mode="auto",
        budget={"credits": 3},
        metadata={"source": "test"},
    )

    assert payload["schema_version"] == 1
    assert payload["connector_ids"] == ["github", "drive"]
    assert payload["uploaded_files"] == [{"name": "a.txt"}]
    assert payload["runtime_config"] == {"gemini_provider": "apiKey"}
    assert payload["autonomy_mode"] == "auto"


def test_artifact_blob_name_is_canonical() -> None:
    assert (
        artifact_blob_name("session-1", "run-1", "outputs\\report.pdf")
        == "session-1/run-1/outputs/report.pdf"
    )


def test_artifact_storage_metadata_contains_regeneration_fields() -> None:
    metadata = artifact_storage_metadata("session-1", "run-1", "outputs/report.pdf")

    assert metadata["gcs_bucket"]
    assert metadata["gcs_blob"] == "session-1/run-1/outputs/report.pdf"


def test_upload_artifact_uses_short_lived_signed_url(monkeypatch) -> None:
    captured = {}

    class FakeBlob:
        def upload_from_string(self, content, content_type=None):
            captured["content_type"] = content_type

        def generate_signed_url(self, *, version, expiration, method):
            captured["expiration"] = expiration
            return "https://signed.example/artifact"

    class FakeBucket:
        def blob(self, name):
            captured["blob_name"] = name
            return FakeBlob()

    class FakeClient:
        def get_bucket(self, name):
            captured["bucket"] = name
            return FakeBucket()

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(storage, "_storage_client", FakeClient())

    url = storage.upload_artifact("session-1", "run-1", "outputs/report.txt", "hello")

    assert url == "https://signed.example/artifact"
    assert captured["expiration"].total_seconds() == 900
    assert captured["blob_name"] == "session-1/run-1/outputs/report.txt"


def test_upload_artifact_does_not_create_bucket_in_production(monkeypatch) -> None:
    captured = {"create_called": False}

    class FakeClient:
        def get_bucket(self, name):
            raise RuntimeError("missing bucket")

        def create_bucket(self, name, location):
            captured["create_called"] = True
            raise AssertionError("production code must not create buckets")

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(storage, "_storage_client", FakeClient())

    assert storage.upload_artifact("session-1", "run-1", "outputs/report.txt", "hello") is None
    assert captured["create_called"] is False


def test_worker_token_is_mandatory(monkeypatch) -> None:
    monkeypatch.setattr(settings, "task_worker_auth_token", "")

    with pytest.raises(HTTPException) as exc_info:
        _validate_worker_token(None)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_task_queue_disabled_returns_noop(monkeypatch) -> None:
    monkeypatch.setattr(settings, "task_worker_enabled", False)

    result = await TaskQueue().enqueue_task_run(task_id="task-1", run_id="run-1")

    assert result.queued is False
    assert result.provider == "none"
    assert "disabled" in result.reason.lower()


@pytest.mark.asyncio
async def test_legacy_task_endpoint_reads_canonical_durable_task_first(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    durable_task = DurableTask(
        task_id="task_1",
        owner_id="user_1",
        title="Durable work",
        status="waiting_approval",
        created_at=now,
        updated_at=now,
        session_id="session_1",
        current_run_id="run_1",
    )
    production_repo = SimpleNamespace(get_task=AsyncMock(return_value=durable_task))
    history_repo = SimpleNamespace(get_task=AsyncMock())

    monkeypatch.setattr(sessions_router, "get_production_task_repository", lambda: production_repo)
    monkeypatch.setattr(sessions_router, "get_history_repository", lambda: history_repo)

    result = await sessions_router.get_task("task_1", user=SimpleNamespace(uid="user_1"))

    assert result.task_id == "task_1"
    assert result.status == "running"
    assert result.current_run_id == "run_1"
    history_repo.get_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_worker_executes_claimed_run_through_orchestrator(monkeypatch) -> None:
    task = SimpleNamespace(
        task_id="task_1",
        owner_id="user_1",
        title="Durable task",
        input_text="do the work",
        session_id=None,
    )
    run = SimpleNamespace(
        execution_payload={
            "input_text": "do the work",
            "session_id": "session_1",
            "connector_ids": ["github"],
            "uploaded_files": [{"name": "a.txt"}],
            "metadata": {"user_transcript_recorded": True},
        }
    )
    repo = SimpleNamespace(get_task=AsyncMock(return_value=task), get_run=AsyncMock(return_value=run))
    session_manager = SimpleNamespace(history_repository=SimpleNamespace())
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run(self, request):
            captured["request"] = request
            return SimpleNamespace(status="completed", summary="Agent turn completed.")

    monkeypatch.setattr(task_worker_module, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(task_worker_module, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(task_worker_module, "AgentTurnRunner", FakeRunner)

    result = await TaskWorker(worker_id="worker_1")._execute_claimed_run(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
    )

    assert result == WorkerRunResult("completed", "Agent turn completed.")
    assert captured["production_task_repository"] is repo
    request = captured["request"]
    assert request.task_id == "task_1"
    assert request.run_id == "run_1"
    assert request.session_id == "session_1"
    assert request.input_text == "do the work"
    assert request.connector_ids == ["github"]
    assert request.uploaded_files == [{"name": "a.txt"}]
    assert request.emit_user_transcript is False


@pytest.mark.asyncio
async def test_task_worker_finishes_cancelled_runs_as_cancelled(monkeypatch) -> None:
    finished: dict[str, object] = {}

    class FakeRepo:
        async def claim_run(self, **kwargs):
            return SimpleNamespace(owner_id="user_1")

        async def append_event(self, **kwargs):
            return None

        async def finish_run(self, **kwargs):
            finished.update(kwargs)

    class CancelWorker(TaskWorker):
        async def _execute_claimed_run(self, *, task_id: str, run_id: str, owner_id: str):
            return WorkerRunResult("cancelled", "Stopped.")

    monkeypatch.setattr(task_worker_module, "get_production_task_repository", lambda: FakeRepo())

    result = await CancelWorker(worker_id="worker_1").run_once(task_id="task_1", run_id="run_1")

    assert result.status == "cancelled"
    assert finished["status"] == "cancelled"
    assert finished["error"] == "Stopped."


@pytest.mark.asyncio
async def test_lifecycle_filters_and_cleans_stale_active_sandboxes(monkeypatch) -> None:
    cleaned: list[tuple[str, str]] = []

    class FakeHistoryRepo:
        async def list_active_sessions(self, owner_id):
            return [
                {"session_id": "alive-session", "sandbox_id": "sandbox-alive"},
                {"session_id": "dead-session", "sandbox_id": "sandbox-dead"},
            ]

        async def mark_session_sandbox_unavailable(self, session_id, *, reason):
            cleaned.append((session_id, reason))

    async def fake_running_ids(e2b_api_key=""):
        return {"sandbox-alive"}

    monkeypatch.setattr(sandbox_module, "list_running_e2b_sandbox_ids", fake_running_ids)

    controller = SandboxLifecycleController(FakeHistoryRepo(), e2b_api_key="test-key")
    sessions = await controller.list_verified_active_sessions("owner-1")

    assert [session["session_id"] for session in sessions] == ["alive-session"]
    assert sessions[0]["sandbox_verification"] == "verified"
    assert cleaned == [("dead-session", "sandbox_not_running")]
