from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.auth import AuthenticatedUser
from nexus import server


class BetaServerSmokeTests(TestCase):
    def setUp(self) -> None:
        self._previous_beta_access_enabled = server.settings.beta_access_enabled
        server.settings.beta_access_enabled = True
        server.app.dependency_overrides[server.require_current_user] = lambda: AuthenticatedUser(
            uid="user-123",
            email="tester@example.com",
            display_name="Tester",
        )

    def tearDown(self) -> None:
        server.settings.beta_access_enabled = self._previous_beta_access_enabled
        server.app.dependency_overrides.clear()

    def _make_session_manager(self) -> MagicMock:
        manager = MagicMock()
        manager.active_count = 0
        manager.start_cleanup = MagicMock()
        manager.stop_cleanup = MagicMock()
        manager.destroy_all = AsyncMock()
        manager.create_ticket = MagicMock(return_value="ticket-123")
        return manager

    def test_beta_status_endpoint_returns_pending_review(self) -> None:
        repo = MagicMock()
        repo.upsert_user = AsyncMock()
        repo.get_user_settings = AsyncMock(
            return_value={
                "betaProfile": {
                    "status": "pending_review",
                    "applicationSubmittedAt": "2026-03-22T00:00:00Z",
                    "accessCodeRedeemed": False,
                }
            }
        )
        repo.get_beta_application = AsyncMock(
            return_value={
                "fullName": "Tester",
                "email": "tester@example.com",
                "role": "Engineer",
                "companyTeam": "QA",
                "primaryUseCase": "Validate session gating",
                "currentWorkflow": "Manual smoke testing",
                "whyAccess": "Need to verify internal beta",
                "expectedUsageFrequency": "Daily",
                "acknowledgeByok": True,
                "status": "pending_review",
                "sheetSync": {"status": "synced"},
            }
        )

        with (
            patch.object(server, "history_repository", repo),
            patch.object(server, "session_manager", self._make_session_manager()),
        ):
            with TestClient(server.app) as client:
                response = client.get("/api/v1/beta/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "pending_review")
        self.assertFalse(body["can_access_app"])
        self.assertTrue(body["can_apply"] is False)

    def test_create_session_rejects_pending_beta_user(self) -> None:
        repo = MagicMock()
        repo.upsert_user = AsyncMock()
        repo.get_user_settings = AsyncMock(
            return_value={"betaProfile": {"status": "pending_review", "accessCodeRedeemed": False}}
        )

        with (
            patch.object(server, "history_repository", repo),
            patch.object(server, "session_manager", self._make_session_manager()),
        ):
            with TestClient(server.app) as client:
                response = client.post("/sessions", json={"mode": "fresh"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "BETA_APPROVAL_PENDING")

    def test_create_session_allows_approved_redeemed_user(self) -> None:
        repo = MagicMock()
        repo.upsert_user = AsyncMock()
        repo.get_user_settings = AsyncMock(
            return_value={"betaProfile": {"status": "approved", "accessCodeRedeemed": True}}
        )
        repo.get_user_quota = AsyncMock(return_value={"remaining": 100, "used": 0, "limit": 4000})
        repo.get_session = AsyncMock(return_value=None)

        session = SimpleNamespace(
            id="session-123",
            stream_url=None,
            status="ready",
            created_at="2026-03-22T00:00:00Z",
            resume_source_session_id=None,
            current_run_id=None,
            run_status=None,
            artifact_count=0,
            exact_workspace_resume_available=False,
            continuation_mode=None,
        )
        manager = self._make_session_manager()
        manager.create_session = AsyncMock(return_value=session)

        with (
            patch.object(server, "history_repository", repo),
            patch.object(server, "session_manager", manager),
            patch.object(
                server,
                "get_byok_status",
                return_value=SimpleNamespace(configured=True, missing=()),
            ),
        ):
            with TestClient(server.app) as client:
                response = client.post("/sessions", json={"mode": "fresh"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "session-123")
        self.assertEqual(body["ws_ticket"], "ticket-123")
