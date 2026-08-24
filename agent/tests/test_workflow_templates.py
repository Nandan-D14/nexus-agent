# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.history_models import StoredWorkflowTemplate
from nexus import dependencies
from nexus import server
from nexus.routers.templates import _build_template_defaults, _normalize_template_input_fields
from nexus.models import WorkflowTemplateInputField


NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def _stored_template(**kwargs) -> StoredWorkflowTemplate:
    defaults = dict(
        template_id="tmpl123abc45",
        owner_id="user-123",
        name="Competitor research",
        description="Reusable research workflow",
        source_session_id=None,
        source_run_id=None,
        instructions="Research the named company.",
        input_fields=[{"key": "company", "label": "Company", "placeholder": "Acme", "required": True}],
        source_artifacts=[],
        created_at=NOW,
        updated_at=NOW,
        last_used_at=None,
    )
    defaults.update(kwargs)
    return StoredWorkflowTemplate(**defaults)


class TemplateHelperTests(TestCase):
    def test_normalize_skips_blank_and_duplicate_keys(self) -> None:
        fields = [
            WorkflowTemplateInputField(key="Company Name", label="Company", placeholder="Acme", required=True),
            WorkflowTemplateInputField(key="company_name", label="Dup", placeholder="", required=False),
            WorkflowTemplateInputField(key="   ", label="Empty", placeholder="", required=False),
            WorkflowTemplateInputField(key="1target", label="Target", placeholder="", required=False),
        ]
        normalized = _normalize_template_input_fields(fields)
        self.assertEqual(
            normalized,
            [
                {"key": "company_name", "label": "Company", "placeholder": "Acme", "required": True},
                {"key": "field_1target", "label": "Target", "placeholder": "", "required": False},
            ],
        )

    def test_build_defaults_requires_saved_context(self) -> None:
        session = SimpleNamespace(
            title="Untitled",
            summary=None,
            handoff_summary={},
            context_packet={},
        )
        with self.assertRaises(Exception) as raised:
            _build_template_defaults(session, None, [], [])
        self.assertEqual(raised.exception.status_code, 400)

    def test_build_defaults_from_session_summary(self) -> None:
        session = SimpleNamespace(
            title="Acme research",
            summary="Looked up competitors",
            handoff_summary={"goal": "Find rivals", "preview": "Looked up competitors"},
            context_packet={},
        )
        defaults = _build_template_defaults(session, None, [], [])
        self.assertEqual(defaults["name"], "Acme research")
        self.assertIn("Original goal: Find rivals", defaults["instructions"])


class TemplateEndpointSmokeTests(TestCase):
    def setUp(self) -> None:
        server.app.dependency_overrides[require_current_user] = lambda: AuthenticatedUser(
            uid="user-123",
            email="tester@example.com",
            display_name="Tester",
        )

    def tearDown(self) -> None:
        server.app.dependency_overrides.clear()

    def _make_session_manager(self) -> MagicMock:
        manager = MagicMock()
        manager.active_count = 0
        manager.start_cleanup = MagicMock()
        manager.stop_cleanup = MagicMock()
        manager.destroy_all = AsyncMock()
        manager.create_ticket = MagicMock(return_value="ticket-123")
        return manager

    @contextmanager
    def _patched(self, repo: MagicMock):
        with (
            patch.object(dependencies, "session_manager", self._make_session_manager()),
            patch.object(dependencies, "history_repository", repo),
        ):
            yield

    def test_create_blank_template(self) -> None:
        repo = MagicMock()
        created = _stored_template()
        repo.create_workflow_template = AsyncMock(return_value=created)
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/v1/templates",
                    json={
                        "name": "Competitor research",
                        "description": "Reusable research workflow",
                        "instructions": "Research the named company.",
                        "input_fields": [
                            {
                                "key": "company",
                                "label": "Company",
                                "placeholder": "Acme",
                                "required": True,
                            }
                        ],
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["template_id"], "tmpl123abc45")
        self.assertEqual(body["name"], "Competitor research")
        self.assertIsNone(body["source_session_id"])
        repo.create_workflow_template.assert_awaited_once()
        kwargs = repo.create_workflow_template.await_args.kwargs
        self.assertIsNone(kwargs["source_session_id"])
        self.assertEqual(kwargs["name"], "Competitor research")
        self.assertEqual(kwargs["status"], "published")
        self.assertEqual(body["status"], "published")

    def test_create_blank_template_requires_name_and_instructions(self) -> None:
        repo = MagicMock()
        repo.create_workflow_template = AsyncMock()
        with self._patched(repo):
            with TestClient(server.app) as client:
                missing_name = client.post(
                    "/api/v1/templates",
                    json={"instructions": "Do the thing."},
                )
                missing_instructions = client.post(
                    "/api/v1/templates",
                    json={"name": "Untitled"},
                )
        self.assertEqual(missing_name.status_code, 400)
        self.assertEqual(missing_instructions.status_code, 400)
        repo.create_workflow_template.assert_not_called()

    def test_create_from_session_uses_defaults_when_fields_omitted(self) -> None:
        repo = MagicMock()
        session = SimpleNamespace(
            owner_id="user-123",
            status="ended",
            title="Weekly report",
            summary="Wrote the weekly report",
            handoff_summary={"goal": "Write report", "preview": "Wrote the weekly report"},
            context_packet={},
        )
        repo.get_session = AsyncMock(return_value=session)
        repo.refresh_session_handoff = AsyncMock()
        repo.get_session_run = AsyncMock(return_value=SimpleNamespace(run_id="run-1"))
        repo.list_session_steps = AsyncMock(return_value=[])
        repo.list_session_artifacts = AsyncMock(return_value=[])
        repo.create_workflow_template = AsyncMock(
            return_value=_stored_template(
                name="Weekly report",
                source_session_id="sess-1",
                source_run_id="run-1",
            )
        )
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/v1/sessions/sess-1/template",
                    json={},
                )
        self.assertEqual(response.status_code, 200, response.text)
        kwargs = repo.create_workflow_template.await_args.kwargs
        self.assertEqual(kwargs["source_session_id"], "sess-1")
        self.assertEqual(kwargs["name"], "Weekly report")
        self.assertIn("Original goal: Write report", kwargs["instructions"])

    def _empty_session_repo(self) -> MagicMock:
        repo = MagicMock()
        repo.get_session = AsyncMock(
            return_value=SimpleNamespace(
                owner_id="user-123",
                status="active",
                title="Untitled",
                summary=None,
                handoff_summary={},
                context_packet={},
            )
        )
        repo.refresh_session_handoff = AsyncMock()
        repo.get_session_run = AsyncMock(return_value=None)
        repo.list_session_steps = AsyncMock(return_value=[])
        repo.list_session_artifacts = AsyncMock(return_value=[])
        return repo

    def test_save_session_template_uses_manual_fields_when_context_is_thin(self) -> None:
        repo = self._empty_session_repo()
        repo.create_workflow_template = AsyncMock(
            return_value=_stored_template(name="Manual name", instructions="Do it anyway.")
        )
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/v1/sessions/sess-empty/template",
                    json={"name": "Manual name", "instructions": "Do it anyway."},
                )
        self.assertEqual(response.status_code, 200, response.text)
        kwargs = repo.create_workflow_template.await_args.kwargs
        self.assertEqual(kwargs["name"], "Manual name")
        self.assertEqual(kwargs["instructions"], "Do it anyway.")
        self.assertEqual(kwargs["source_session_id"], "sess-empty")

    def test_save_session_template_rejects_empty_context_without_manual_fields(self) -> None:
        repo = self._empty_session_repo()
        repo.create_workflow_template = AsyncMock()
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/v1/sessions/sess-empty/template",
                    json={},
                )
        self.assertEqual(response.status_code, 400)
        self.assertIn("enough saved context", response.json()["detail"])
        repo.create_workflow_template.assert_not_called()

    def test_update_template(self) -> None:
        repo = MagicMock()
        repo.update_workflow_template = AsyncMock(
            return_value=_stored_template(name="Updated name", instructions="New instructions")
        )
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.patch(
                    "/api/v1/templates/tmpl123abc45",
                    json={"name": "Updated name", "instructions": "New instructions"},
                )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "Updated name")
        repo.update_workflow_template.assert_awaited_once()

    def test_list_templates_serializes_null_source_session(self) -> None:
        repo = MagicMock()
        repo.list_workflow_templates = AsyncMock(return_value=[_stored_template()])
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.get("/api/v1/templates")
        self.assertEqual(response.status_code, 200, response.text)
        templates = response.json()["templates"]
        self.assertEqual(len(templates), 1)
        self.assertIsNone(templates[0]["source_session_id"])
        self.assertEqual(templates[0]["status"], "published")

    def test_create_draft_template(self) -> None:
        repo = MagicMock()
        created = _stored_template(status="draft")
        repo.create_workflow_template = AsyncMock(return_value=created)
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/v1/templates",
                    json={
                        "name": "Competitor research",
                        "instructions": "Research the named company.",
                        "status": "draft",
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "draft")
        kwargs = repo.create_workflow_template.await_args.kwargs
        self.assertEqual(kwargs["status"], "draft")

    def test_publish_template(self) -> None:
        repo = MagicMock()
        repo.get_workflow_template = AsyncMock(return_value=_stored_template(status="draft"))
        repo.update_workflow_template = AsyncMock(
            return_value=_stored_template(status="published")
        )
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.patch(
                    "/api/v1/templates/tmpl123abc45",
                    json={"status": "published"},
                )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "published")
        kwargs = repo.update_workflow_template.await_args.kwargs
        self.assertEqual(kwargs["status"], "published")

    def test_run_rejects_draft(self) -> None:
        repo = MagicMock()
        repo.get_workflow_template = AsyncMock(return_value=_stored_template(status="draft"))
        with self._patched(repo):
            with TestClient(server.app) as client:
                response = client.post("/api/v1/templates/tmpl123abc45/run", json={})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Publish this template", response.json()["detail"])
