from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import server
from nexus.orchestrator import NexusOrchestrator


class SafeWorkspacePathTests(TestCase):
    def test_safe_workspace_relative_path_preserves_valid_upload_path(self) -> None:
        self.assertEqual(
            server._safe_workspace_relative_path("sources/uploads/report.pdf"),
            "sources/uploads/report.pdf",
        )

    def test_safe_workspace_relative_path_rejects_parent_segments(self) -> None:
        with self.assertRaises(Exception):
            server._safe_workspace_relative_path("../report.pdf")


class DriveMirrorTests(IsolatedAsyncioTestCase):
    async def test_mirror_upload_to_google_drive_skips_when_drive_not_connected(self) -> None:
        with patch.object(server, "get_google_drive_client_for_user", new=AsyncMock(return_value=None)):
            result = await server._mirror_upload_to_google_drive(
                user_id="user-1",
                session_id="session-1",
                filename="report.pdf",
                content=b"hello",
                mime_type="application/pdf",
            )

        self.assertEqual(result, {"status": "skipped"})

    async def test_mirror_upload_to_google_drive_uploads_into_cocomputer_folder(self) -> None:
        fake_client = MagicMock()
        fake_client.ensure_folder_path = AsyncMock(
            return_value={
                "folder_id": "folder-1",
                "path": "CoComputer/Sessions/session-1/Uploads",
            }
        )
        fake_client.upload_bytes = AsyncMock(
            return_value={
                "id": "file-1",
                "webViewLink": "https://drive.google.com/file/d/file-1/view",
            }
        )

        with patch.object(server, "get_google_drive_client_for_user", new=AsyncMock(return_value=fake_client)):
            result = await server._mirror_upload_to_google_drive(
                user_id="user-1",
                session_id="session-1",
                filename="report.pdf",
                content=b"hello",
                mime_type="application/pdf",
            )

        self.assertEqual(result["status"], "uploaded")
        self.assertEqual(result["drive_file_id"], "file-1")
        self.assertEqual(result["folder_path"], "CoComputer/Sessions/session-1/Uploads")
        fake_client.ensure_folder_path.assert_awaited_once_with(
            ["CoComputer", "Sessions", "session-1", "Uploads"]
        )


class TurnContextFormattingTests(TestCase):
    def test_format_turn_context_includes_connectors_and_uploaded_files(self) -> None:
        orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)

        result = orchestrator._format_turn_context(
            ["google_drive", "system"],
            [
                {
                    "name": "report.pdf",
                    "path": "/workspace/session/run/sources/uploads/report.pdf",
                    "mime_type": "application/pdf",
                    "drive_web_view_link": "https://drive.google.com/file/d/file-1/view",
                }
            ],
        )

        self.assertIn("[USER-SELECTED CONNECTORS]", result)
        self.assertIn("google_drive, system", result)
        self.assertIn("[UPLOADED FILES]", result)
        self.assertIn("report.pdf", result)
        self.assertIn("/workspace/session/run/sources/uploads/report.pdf", result)
