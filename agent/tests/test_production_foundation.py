# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.config import settings
from nexus.policy import evaluate_tool_policy
from nexus import storage
from nexus.routers.worker import _validate_worker_token
from nexus.storage import artifact_blob_name, artifact_storage_metadata
from nexus.task_queue import TaskQueue


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
