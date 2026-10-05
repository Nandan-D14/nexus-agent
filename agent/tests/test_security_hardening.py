"""Regression tests for authorization / input-validation hardening."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from nexus.models import UserSettingsUpdateRequest
from nexus.routers import tasks as tasks_router
from nexus.routers import worker as worker_router
from nexus.task_budget import TaskBudgetGuard


def test_user_settings_rejects_server_owned_fields() -> None:
    for field in ("creditLimit", "planId", "tokenLimit", "integrations", "googleDriveRefreshToken"):
        with pytest.raises(ValidationError):
            UserSettingsUpdateRequest.model_validate({field: 1})


def test_user_settings_accepts_preferences_and_byok() -> None:
    parsed = UserSettingsUpdateRequest.model_validate(
        {"settings": {"voice": {"voiceId": "a"}}, "byok": {"llmModel": "m"}}
    )
    assert parsed.settings == {"voice": {"voiceId": "a"}}


def test_budget_can_lower_but_not_raise_server_limits(monkeypatch) -> None:
    monkeypatch.setattr("nexus.task_budget.settings.default_task_max_tool_calls", 80)
    monkeypatch.setattr("nexus.task_budget.settings.default_task_budget_credits", 1000)
    monkeypatch.setattr("nexus.task_budget.settings.default_task_max_runtime_minutes", 60)

    raised = TaskBudgetGuard.from_budget({"maxToolCalls": 10_000, "credits": 10**9, "maxRuntimeMinutes": 10**6})
    assert raised.max_tool_calls == 80
    assert raised.max_credits == 1000
    assert raised.max_runtime_seconds == 3600

    lowered = TaskBudgetGuard.from_budget({"maxToolCalls": 5, "credits": 3, "maxRuntimeMinutes": 1})
    assert (lowered.max_tool_calls, lowered.max_credits, lowered.max_runtime_seconds) == (5, 3, 60)


def test_task_metadata_strips_server_only_flags() -> None:
    cleaned = tasks_router._client_metadata(
        {"skip_confirmations": True, "allowed_unattended_tools": ["*"], "note": "keep"}
    )
    assert cleaned == {"note": "keep"}


def test_task_request_rejects_oversized_json() -> None:
    with pytest.raises(ValidationError):
        tasks_router.DurableTaskCreateRequest(metadata={"blob": "x" * (70 * 1024)})


@pytest.mark.asyncio
async def test_task_cannot_attach_to_foreign_session(monkeypatch) -> None:
    class Repo:
        async def get_session(self, session_id):
            return SimpleNamespace(owner_id="victim")

    monkeypatch.setattr(tasks_router, "get_history_repository", lambda: Repo())

    with pytest.raises(HTTPException) as exc:
        await tasks_router._require_session_access("victim-session", "attacker")
    assert exc.value.status_code == 404
    await tasks_router._require_session_access("victim-session", "victim")


def test_queue_payload_hides_resource_names() -> None:
    enqueue = SimpleNamespace(queued=True, provider="cloud_tasks", name="projects/p/queues/q/tasks/t", reason="boom")
    assert tasks_router._queue_payload(enqueue) == {"queued": True, "provider": "cloud_tasks"}


def test_upsert_session_refuses_owner_change(monkeypatch) -> None:
    import nexus._firestore_base as firestore_base
    from nexus.history_repository import FirestoreHistoryRepository

    snapshot = SimpleNamespace(exists=True, to_dict=lambda: {"ownerId": "victim"})
    ref = SimpleNamespace(get=lambda: snapshot)
    fake_db = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda _id: ref))
    monkeypatch.setattr(firestore_base, "get_firestore_client", lambda: fake_db)
    repo = FirestoreHistoryRepository.__new__(FirestoreHistoryRepository)
    session = SimpleNamespace(id="s1", owner_id="attacker", task_id="t1")

    with pytest.raises(PermissionError):
        repo._upsert_session_sync(session, "active", None, None)


@pytest.mark.asyncio
async def test_unattended_runs_deny_instead_of_auto_approving() -> None:
    from nexus.policy import ToolPolicyDecision
    from nexus.tool_gateway import _await_approval
    from nexus.tools._context import set_skip_confirmations

    token = set_skip_confirmations(True)
    try:
        decision = ToolPolicyDecision("require_approval", "needs a human", "high")
        assert await _await_approval("git_push", decision, {}) is False
    finally:
        from nexus.tools._context import _current_skip_confirmations

        _current_skip_confirmations.reset(token)


def test_worker_token_check(monkeypatch) -> None:
    monkeypatch.setattr(worker_router.settings, "task_worker_auth_token", "s3cret-token")
    worker_router._validate_worker_token("s3cret-token")
    for bad in (None, "", "s3cret-tokeX"):
        with pytest.raises(HTTPException) as exc:
            worker_router._validate_worker_token(bad)
        assert exc.value.status_code == 403
