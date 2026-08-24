# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.library_artifacts import (
    is_library_artifact,
    library_category,
    matches_library_search,
)
from nexus import dependencies
from nexus import server


def _artifact(**kwargs):
    defaults = {
        "kind": "document",
        "title": "Report.docx",
        "preview": "Quarterly summary",
        "path": "outputs/Report.docx",
        "metadata": {"role": "deliverable", "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class LibraryArtifactClassificationTests(TestCase):
    def test_keeps_html_and_office_deliverables(self) -> None:
        html = _artifact(kind="html", title="Calculator", path=None, metadata={"role": "deliverable"})
        docx = _artifact()
        xlsx = _artifact(
            kind="spreadsheet",
            title="free_trial_companies.xlsx",
            path="outputs/free_trial_companies.xlsx",
            metadata={
                "role": "deliverable",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        )
        self.assertTrue(is_library_artifact(html))
        self.assertTrue(is_library_artifact(docx))
        self.assertTrue(is_library_artifact(xlsx))
        self.assertEqual(library_category(html), "others")
        self.assertEqual(library_category(docx), "documents")
        self.assertEqual(library_category(xlsx), "spreadsheets")

    def test_excludes_scrapes_and_source_dumps(self) -> None:
        scrape = _artifact(
            kind="export_reference",
            title="Scraped page",
            path="sources/example.md",
            metadata={"role": "source", "tool": "scrape_web_page"},
        )
        search = _artifact(
            kind="export_reference",
            title="Search dump",
            path="sources/search.md",
            metadata={"tool": "web_search"},
        )
        screenshot = _artifact(
            kind="screenshot_reference",
            title="Screenshot capture",
            path=None,
            metadata={"role": "source", "tool": "take_screenshot"},
        )
        self.assertFalse(is_library_artifact(scrape))
        self.assertFalse(is_library_artifact(search))
        self.assertFalse(is_library_artifact(screenshot))

    def test_excludes_sources_path_even_without_role(self) -> None:
        legacy = _artifact(
            kind="file",
            title="page.md",
            path="sources/page.md",
            metadata={},
        )
        self.assertFalse(is_library_artifact(legacy))

    def test_classifies_slides_and_media_from_filename(self) -> None:
        slides = _artifact(
            kind="uploaded_file",
            title="Pitch.pptx",
            path="uploads/Pitch.pptx",
            metadata={"role": "deliverable", "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        )
        video = _artifact(
            kind="uploaded_file",
            title="Welcome.mp4",
            path="uploads/Welcome.mp4",
            metadata={"role": "deliverable", "content_type": "video/mp4"},
        )
        self.assertEqual(library_category(slides), "slides")
        self.assertEqual(library_category(video), "media")

    def test_search_matches_title_preview_and_session(self) -> None:
        artifact = _artifact(title="Investor brief", preview="Series A outreach")
        self.assertTrue(matches_library_search(artifact, "Seeking Investment", "investor"))
        self.assertTrue(matches_library_search(artifact, "Seeking Investment", "series a"))
        self.assertTrue(matches_library_search(artifact, "Seeking Investment", "seeking"))
        self.assertFalse(matches_library_search(artifact, "Seeking Investment", "scrape"))


class LibraryEndpointSmokeTests(TestCase):
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

    def test_library_requires_auth(self) -> None:
        server.app.dependency_overrides.clear()
        with (
            patch.object(dependencies, "session_manager", self._make_session_manager()),
            patch.object(dependencies, "history_repository", MagicMock()),
        ):
            with TestClient(server.app) as client:
                response = client.get("/api/v1/library")
        self.assertEqual(response.status_code, 401)

    def test_library_empty_list(self) -> None:
        repo = MagicMock()
        repo.list_owner_library_artifacts = AsyncMock(return_value=([], None))
        with (
            patch.object(dependencies, "session_manager", self._make_session_manager()),
            patch.object(dependencies, "history_repository", repo),
        ):
            with TestClient(server.app) as client:
                response = client.get("/api/v1/library")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "next_cursor": None})
        repo.list_owner_library_artifacts.assert_awaited_once()

    def test_library_rejects_unknown_category(self) -> None:
        repo = MagicMock()
        repo.list_owner_library_artifacts = AsyncMock(return_value=([], None))
        with (
            patch.object(dependencies, "session_manager", self._make_session_manager()),
            patch.object(dependencies, "history_repository", repo),
        ):
            with TestClient(server.app) as client:
                response = client.get("/api/v1/library?category=websites")
        self.assertEqual(response.status_code, 400)

    def test_library_serializes_deliverable_item(self) -> None:
        from datetime import datetime, timezone

        from nexus.history_models import StoredArtifact
        from nexus.library_artifacts import LibraryListRow

        artifact = StoredArtifact(
            artifact_id="abc123def456",
            run_id="run1",
            session_id="sess1",
            task_id="sess1",
            kind="html",
            title="Calculator",
            preview="A calculator",
            created_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
            metadata={"role": "deliverable"},
        )
        repo = MagicMock()
        repo.list_owner_library_artifacts = AsyncMock(
            return_value=(
                [LibraryListRow(artifact=artifact, session_title="Demo session", category="others")],
                None,
            )
        )
        with (
            patch.object(dependencies, "session_manager", self._make_session_manager()),
            patch.object(dependencies, "history_repository", repo),
        ):
            with TestClient(server.app) as client:
                response = client.get("/api/v1/library")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["session_title"], "Demo session")
        self.assertEqual(payload["items"][0]["category"], "others")
        self.assertEqual(payload["items"][0]["artifact"]["kind"], "html")
        self.assertEqual(payload["items"][0]["artifact"]["title"], "Calculator")


class LibraryIndexFallbackTests(TestCase):
    def test_library_lists_via_sessions_without_owner_collection_group(self) -> None:
        from datetime import datetime, timezone

        from nexus.history_models import StoredArtifact
        from nexus.history_repository import FirestoreHistoryRepository

        repo = FirestoreHistoryRepository()
        artifact = StoredArtifact(
            artifact_id="abc123def456",
            run_id="run1",
            session_id="sess1",
            task_id="sess1",
            kind="document",
            title="Report.docx",
            preview="Quarterly",
            created_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
            metadata={
                "role": "deliverable",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        )
        with (
            patch.object(
                repo,
                "_list_owner_sessions_sync",
                return_value=[
                    (
                        "sess1",
                        {"title": "Investor brief", "hasArtifacts": True, "status": "ended"},
                    )
                ],
            ),
            patch.object(repo, "_list_session_run_artifacts_sync", return_value=[artifact]),
            patch.object(
                repo,
                "_list_owner_library_artifacts_collection_group_sync",
                side_effect=AssertionError("owner collection-group query must not run"),
            ),
        ):
            rows, cursor = repo._list_owner_library_artifacts_sync(
                "user-123",
                50,
                None,
                None,
                None,
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].session_title, "Investor brief")
        self.assertEqual(rows[0].category, "documents")
        self.assertIsNone(cursor)

    def test_fallback_still_drops_scrapes(self) -> None:
        from datetime import datetime, timezone

        from nexus.history_models import StoredArtifact
        from nexus.history_repository import FirestoreHistoryRepository

        repo = FirestoreHistoryRepository()
        scrape = StoredArtifact(
            artifact_id="scrapedoc001",
            run_id="run1",
            session_id="sess1",
            task_id="sess1",
            kind="export_reference",
            title="Scraped page",
            preview="source dump",
            created_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
            path="sources/page.md",
            metadata={"role": "source", "tool": "scrape_web_page"},
        )
        with (
            patch.object(repo, "_list_owner_sessions_sync", return_value=[
                ("sess1", {"title": "Research", "hasArtifacts": True, "status": "ended"}),
            ]),
            patch.object(repo, "_list_session_run_artifacts_sync", return_value=[scrape]),
        ):
            rows, _cursor = repo._list_owner_library_artifacts_via_sessions_sync(
                "user-123",
                50,
                None,
                None,
                None,
            )
        self.assertEqual(rows, [])
