# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""GCS artifact storage helpers."""

import logging
from datetime import timedelta
from typing import Optional

from google.cloud import storage

from nexus.config import settings

logger = logging.getLogger(__name__)

_storage_client: Optional[storage.Client] = None

def get_storage_client() -> storage.Client:
    """Initialize and return the GCS client."""
    global _storage_client
    if _storage_client is None:
        try:
            # Use explicit project to avoid issues if ADC doesn't infer it
            project_id = settings.google_project_id or settings.firebase_project_id
            _storage_client = storage.Client(project=project_id)
        except Exception as e:
            logger.warning("Failed to initialize storage client with project %s: %s", project_id, e)
            _storage_client = storage.Client()
    return _storage_client

def get_artifact_bucket_name() -> str:
    """Return the environment-specific bucket name."""
    env = settings.app_env.lower() if settings.app_env else "development"
    return f"nexus-artifacts-{env}"

def upload_artifact(session_id: str, run_id: str, relative_path: str, content: str | bytes) -> Optional[str]:
    """Uploads a file to GCS and returns a signed URL."""
    try:
        client = get_storage_client()
        bucket_name = get_artifact_bucket_name()
        
        try:
            bucket = client.get_bucket(bucket_name)
        except Exception:
            logger.info("Bucket %s not found, attempting to create it", bucket_name)
            try:
                bucket = client.create_bucket(bucket_name, location="US")
            except Exception as create_exc:
                logger.error("Failed to create bucket %s: %s", bucket_name, create_exc)
                return None

        blob_name = f"{session_id}/{run_id}/{relative_path}"
        blob = bucket.blob(blob_name)
        
        if isinstance(content, str):
            blob.upload_from_string(content, content_type="text/plain; charset=utf-8")
        else:
            blob.upload_from_string(content)

        url = blob.generate_signed_url(version="v4", expiration=timedelta(days=7), method="GET")
        return url
    except Exception as e:
        logger.error("Failed to upload artifact %s to GCS: %s", relative_path, e)
        return None

async def upload_artifact_async(session_id: str, run_id: str, relative_path: str, content: str | bytes) -> Optional[str]:
    """Async wrapper for upload_artifact."""
    import asyncio
    return await asyncio.to_thread(upload_artifact, session_id, run_id, relative_path, content)

async def delete_user_artifacts_async(user_id: str, session_ids: list[str]) -> None:
    """Deletes all artifacts in GCS associated with the user's sessions."""
    import asyncio
    
    def _delete_sync():
        try:
            client = get_storage_client()
            bucket_name = get_artifact_bucket_name()
            try:
                bucket = client.get_bucket(bucket_name)
            except Exception:
                return # Bucket doesn't exist
            
            for session_id in session_ids:
                blobs = list(bucket.list_blobs(prefix=f"{session_id}/"))
                if blobs:
                    bucket.delete_blobs(blobs)
                    logger.info("Deleted %d artifacts for session %s", len(blobs), session_id)
        except Exception as exc:
            logger.error("Failed to delete user artifacts from GCS: %s", exc)

    await asyncio.to_thread(_delete_sync)
