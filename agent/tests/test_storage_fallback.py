# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.storage import download_artifact_as_data_uri, parse_gcs_object_url, preview_artifact_gcs_location, preview_media_type
from nexus.routers.tasks import download_artifact_by_id, download_artifact_content


class StorageFallbackUnitTests(TestCase):
    @patch("nexus.storage.get_storage_client")
    def test_download_artifact_as_data_uri_success(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mock_blob.exists.return_value = True
        mock_blob.size = 1024
        mock_blob.content_type = "image/png"
        mock_blob.download_as_bytes.return_value = b"fake-png-content"

        result = download_artifact_as_data_uri(bucket_name="test-bucket", blob_name="test-blob.png")

        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("data:image/png;base64,"))
        self.assertIn("ZmFrZS1wbmctY29udGVudA==", result)  # base64 for 'fake-png-content'
        mock_client.bucket.assert_called_once_with("test-bucket")
        mock_bucket.blob.assert_called_once_with("test-blob.png")
        mock_blob.exists.assert_called_once()
        mock_blob.download_as_bytes.assert_called_once()

    @patch("nexus.storage.get_storage_client")
    def test_download_artifact_as_data_uri_exceeds_max_bytes(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mock_blob.exists.return_value = True
        mock_blob.size = 10 * 1024 * 1024  # 10 MB

        result = download_artifact_as_data_uri(
            bucket_name="test-bucket",
            blob_name="test-blob.png",
            max_bytes=5 * 1024 * 1024,
        )

        self.assertIsNone(result)
        mock_blob.download_as_bytes.assert_not_called()

    @patch("nexus.storage.get_storage_client")
    def test_download_artifact_as_data_uri_non_existent(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mock_blob.exists.return_value = False

        result = download_artifact_as_data_uri(bucket_name="test-bucket", blob_name="test-blob.png")

        self.assertIsNone(result)
        mock_blob.download_as_bytes.assert_not_called()


class RouterDownloadFallbackTests(IsolatedAsyncioTestCase):
    @patch("nexus.routers.tasks.get_history_repository")
    @patch("nexus.routers.tasks.generate_artifact_signed_url")
    @patch("nexus.routers.tasks.download_artifact_as_data_uri")
    async def test_download_artifact_by_id_falls_back_to_data_uri(
        self,
        mock_download_data_uri: MagicMock,
        mock_generate_signed: MagicMock,
        mock_get_history_repo: MagicMock,
    ) -> None:
        # Mock Artifact DB record
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "artifact-123"
        mock_artifact.url = "https://storage.googleapis.com/test-bucket/test-blob.png"
        mock_artifact.metadata = {
            "gcs_bucket": "test-bucket",
            "gcs_blob": "test-blob.png",
        }

        mock_history_repo = MagicMock()
        mock_history_repo.get_artifact_for_owner = AsyncMock(return_value=mock_artifact)
        mock_get_history_repo.return_value = mock_history_repo

        # Simulate signed URL generation failure (returns None)
        mock_generate_signed.return_value = None
        # Simulate data URI download success
        mock_download_data_uri.return_value = "data:image/png;base64,ZmFrZS1wbmctY29udGVudA=="

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        response = await download_artifact_by_id(artifact_id="artifact-123", user=mock_user)

        self.assertEqual(response["artifact_id"], "artifact-123")
        self.assertEqual(response["url"], "data:image/png;base64,ZmFrZS1wbmctY29udGVudA==")
        mock_generate_signed.assert_called_once_with(bucket_name="test-bucket", blob_name="test-blob.png")
        mock_download_data_uri.assert_called_once_with(bucket_name="test-bucket", blob_name="test-blob.png")


class ParseGcsUrlTests(TestCase):
    def test_path_style_signed_url(self) -> None:
        url = (
            "https://storage.googleapis.com/nexus-artifacts-development/"
            "15c0d0aa0b34/58dbc08f39bd/outputs/q1-sales.xlsx"
            "?X-Goog-Algorithm=GOOG4-RSA-SHA256"
        )
        self.assertEqual(
            parse_gcs_object_url(url),
            (
                "nexus-artifacts-development",
                "15c0d0aa0b34/58dbc08f39bd/outputs/q1-sales.xlsx",
            ),
        )

    def test_virtual_hosted_style(self) -> None:
        url = "https://nexus-artifacts-development.storage.googleapis.com/sess/run/file.xlsx"
        self.assertEqual(
            parse_gcs_object_url(url),
            ("nexus-artifacts-development", "sess/run/file.xlsx"),
        )

    def test_non_gcs(self) -> None:
        self.assertIsNone(parse_gcs_object_url("https://drive.google.com/file"))


class RouterContentProxyTests(IsolatedAsyncioTestCase):
    @patch("nexus.routers.tasks.get_history_repository")
    @patch("nexus.routers.tasks.download_artifact_bytes")
    async def test_content_proxies_gcs_bytes_from_url(
        self,
        mock_download_bytes: MagicMock,
        mock_get_history_repo: MagicMock,
    ) -> None:
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "artifact-123"
        mock_artifact.title = "q1-sales.xlsx"
        mock_artifact.url = (
            "https://storage.googleapis.com/test-bucket/sess/run/q1-sales.xlsx"
            "?X-Goog-Signature=abc"
        )
        mock_artifact.metadata = {}

        mock_history_repo = MagicMock()
        mock_history_repo.get_artifact_for_owner = AsyncMock(return_value=mock_artifact)
        mock_get_history_repo.return_value = mock_history_repo
        mock_download_bytes.return_value = (
            b"xlsx-bytes",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        response = await download_artifact_content(artifact_id="artifact-123", user=mock_user)

        self.assertEqual(response.body, b"xlsx-bytes")
        self.assertEqual(
            response.media_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        mock_download_bytes.assert_called_once_with(
            bucket_name="test-bucket",
            blob_name="sess/run/q1-sales.xlsx",
        )

    @patch("nexus.routers.tasks.get_history_repository")
    @patch("nexus.routers.tasks.download_artifact_bytes")
    async def test_content_proxies_preview_sibling(
        self,
        mock_download_bytes: MagicMock,
        mock_get_history_repo: MagicMock,
    ) -> None:
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "artifact-deck"
        mock_artifact.title = "review.pptx"
        mock_artifact.session_id = "sess"
        mock_artifact.run_id = "run"
        mock_artifact.url = "https://storage.googleapis.com/test-bucket/sess/run/outputs/review.pptx"
        mock_artifact.metadata = {
            "gcs_bucket": "test-bucket",
            "gcs_blob": "sess/run/outputs/review.pptx",
            "preview_url": "https://storage.googleapis.com/test-bucket/sess/run/outputs/review.html",
            "preview_path": "outputs/review.html",
            "preview_content_type": "text/html; charset=utf-8",
        }

        mock_history_repo = MagicMock()
        mock_history_repo.get_artifact_for_owner = AsyncMock(return_value=mock_artifact)
        mock_get_history_repo.return_value = mock_history_repo
        mock_download_bytes.return_value = (b"<html>deck</html>", "application/octet-stream")

        mock_user = MagicMock()
        mock_user.uid = "user-123"

        response = await download_artifact_content(
            artifact_id="artifact-deck",
            user=mock_user,
            sibling="preview",
        )

        self.assertEqual(response.body, b"<html>deck</html>")
        self.assertTrue(str(response.media_type).startswith("text/html"))
        self.assertIn("review.html", response.headers["Content-Disposition"])
        mock_download_bytes.assert_called_once_with(
            bucket_name="test-bucket",
            blob_name="sess/run/outputs/review.html",
        )


class PreviewSiblingLocationTests(TestCase):
    def test_preview_location_from_gcs_url(self) -> None:
        self.assertEqual(
            preview_artifact_gcs_location(
                session_id="sess",
                run_id="run",
                metadata={
                    "preview_url": "https://storage.googleapis.com/bucket/sess/run/outputs/deck.html",
                    "gcs_bucket": "bucket",
                    "preview_path": "outputs/deck.html",
                },
            ),
            ("bucket", "sess/run/outputs/deck.html"),
        )

    def test_preview_location_from_path_when_url_missing(self) -> None:
        self.assertEqual(
            preview_artifact_gcs_location(
                session_id="sess",
                run_id="run",
                metadata={
                    "gcs_bucket": "bucket",
                    "preview_path": "outputs/scope.pdf",
                },
            ),
            ("bucket", "sess/run/outputs/scope.pdf"),
        )

    def test_preview_media_type_from_path(self) -> None:
        self.assertEqual(preview_media_type("outputs/deck.html", None), "text/html; charset=utf-8")
        self.assertEqual(preview_media_type("outputs/scope.pdf", None), "application/pdf")
