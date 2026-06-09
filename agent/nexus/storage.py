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
_SIGNED_URL_EXPIRATION_SECONDS = 900

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

def artifact_blob_name(session_id: str, run_id: str, relative_path: str) -> str:
    """Return the canonical object name for a run artifact."""
    cleaned = (relative_path or "artifact.bin").strip().replace("\\", "/")
    cleaned = "/".join(part for part in cleaned.split("/") if part and part != ".")
    return f"{session_id}/{run_id}/{cleaned or 'artifact.bin'}"

def artifact_storage_metadata(session_id: str, run_id: str, relative_path: str) -> dict[str, str]:
    """Metadata needed to regenerate signed URLs later."""
    return {
        "gcs_bucket": get_artifact_bucket_name(),
        "gcs_blob": artifact_blob_name(session_id, run_id, relative_path),
    }

def generate_artifact_signed_url(
    *,
    bucket_name: str,
    blob_name: str,
    expiration_seconds: int = _SIGNED_URL_EXPIRATION_SECONDS,
) -> Optional[str]:
    """Generate a fresh signed URL for an existing artifact object."""
    try:
        client = get_storage_client()
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiration_seconds),
            method="GET",
        )
    except Exception as e:
        logger.error("Failed to generate signed URL for %s/%s: %s", bucket_name, blob_name, e)
        return None

def download_artifact_as_data_uri(
    *,
    bucket_name: str,
    blob_name: str,
    max_bytes: int = 5 * 1024 * 1024,
) -> Optional[str]:
    """Download a GCS blob and return its content as a base64 data URI.

    This bypasses signed URL generation entirely — it reads the blob using
    application default credentials (which always work within the project)
    and encodes the content inline.

    Returns None if the blob doesn't exist or exceeds *max_bytes*.
    """
    try:
        import base64
        import mimetypes

        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        blob.reload()
        if blob.size and blob.size > max_bytes:
            logger.warning(
                "Blob %s/%s is %d bytes, exceeds data-URI limit of %d",
                bucket_name, blob_name, blob.size, max_bytes,
            )
            return None
        content = blob.download_as_bytes()
        mime = blob.content_type or mimetypes.guess_type(blob_name)[0] or "application/octet-stream"
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        logger.exception("Failed to download blob %s/%s as data URI", bucket_name, blob_name)
        return None


def upload_artifact(session_id: str, run_id: str, relative_path: str, content: str | bytes) -> Optional[str]:
    """Uploads a file to GCS and returns a URL (signed if possible, public otherwise)."""
    try:
        client = get_storage_client()
        bucket_name = get_artifact_bucket_name()

        try:
            bucket = client.get_bucket(bucket_name)
        except Exception as bucket_exc:
            if settings.is_production:
                logger.error(
                    "Artifact bucket %s was not found or is not accessible. "
                    "Provision the bucket before running production uploads: %s",
                    bucket_name,
                    bucket_exc,
                )
                return None
            logger.info("Bucket %s not found, attempting to create it", bucket_name)
            try:
                bucket = client.create_bucket(bucket_name, location="US")
            except Exception as create_exc:
                logger.error("Failed to create bucket %s: %s", bucket_name, create_exc)
                return None

        blob_name = artifact_blob_name(session_id, run_id, relative_path)
        blob = bucket.blob(blob_name)

        if isinstance(content, str):
            blob.upload_from_string(content, content_type="text/plain; charset=utf-8")
        else:
            blob.upload_from_string(content)

        # Try signed URL first (requires service account key).
        # Fall back to public URL when running with user credentials (local dev).
        try:
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=_SIGNED_URL_EXPIRATION_SECONDS),
                method="GET",
            )
            return url
        except Exception as sign_exc:
            logger.warning(
                "Signed URL generation failed for %s (expected in local dev without SA key): %s. "
                "Falling back to public URL.",
                blob_name, sign_exc,
            )
            try:
                blob.make_public()
                return blob.public_url
            except Exception as pub_exc:
                logger.warning(
                    "make_public also failed for %s: %s. Returning direct GCS URI.",
                    blob_name, pub_exc,
                )
                return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

    except Exception as e:
        logger.error("Failed to upload artifact %s to GCS: %s", relative_path, e)
        
        # Fallback: Save as a data URI directly in the database if GCS fails
        try:
            import base64
            import mimetypes
            mime, _ = mimetypes.guess_type(relative_path)
            mime = mime or "application/octet-stream"
            
            content_bytes = content.encode("utf-8") if isinstance(content, str) else content
            # Only inline if < 5MB to avoid blowing up Firestore document limits
            if len(content_bytes) < 5 * 1024 * 1024:
                b64 = base64.b64encode(content_bytes).decode("ascii")
                logger.info("Fell back to base64 data URI for %s", relative_path)
                return f"data:{mime};base64,{b64}"
        except Exception as b64_exc:
            logger.error("Failed to encode base64 fallback for %s: %s", relative_path, b64_exc)
            
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
