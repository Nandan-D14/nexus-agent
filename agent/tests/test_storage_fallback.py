# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.storage import download_artifact_as_data_uri
from nexus.routers.tasks import download_artifact_by_id


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
