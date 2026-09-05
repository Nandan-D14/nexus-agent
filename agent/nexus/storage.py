# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""GCS artifact storage helpers."""

import logging
import mimetypes
from datetime import timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from google.cloud import storage
from google.oauth2 import service_account

from nexus.config import AGENT_DIR, WORKSPACE_DIR, settings

logger = logging.getLogger(__name__)

_storage_client: Optional[storage.Client] = None
_SIGNED_URL_EXPIRATION_SECONDS = 900
_CONTENT_MAX_BYTES = 25 * 1024 * 1024


def _resolve_sa_credentials():
    """Load explicit SA credentials from the configured key file.

    Mirrors the resolution logic in firebase.py so that the GCS client can
    generate signed URLs even when GOOGLE_APPLICATION_CREDENTIALS is not
    exported to the environment (which is intentional when google_project_id
    is set, to avoid leaking the Firebase SA into the Vertex AI SDK).
    """
    raw_path = settings.google_application_credentials
    if not raw_path:
        return None

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return service_account.Credentials.from_service_account_file(str(candidate))

    for root in (Path.cwd(), AGENT_DIR, WORKSPACE_DIR):
        resolved = (root / candidate).resolve()
        if resolved.exists():
            logger.info("Loaded GCS SA credentials from %s", resolved)
            return service_account.Credentials.from_service_account_file(str(resolved))

    logger.warning("SA credentials file %s not found; GCS will use ADC (signed URLs may fail)", raw_path)
    return None


def get_storage_client() -> storage.Client:
    """Initialize and return the GCS client."""
    global _storage_client
    if _storage_client is None:
        # Use the Vertex AI project for GCS since it has billing enabled.
        # We will instruct the user to grant the Firebase SA access to this project.
        project_id = settings.google_project_id or settings.firebase_project_id
        try:
            creds = _resolve_sa_credentials()
            if creds:
                _storage_client = storage.Client(project=project_id, credentials=creds)
                logger.info("GCS storage client initialized with explicit SA credentials (project=%s)", project_id)
            else:
                _storage_client = storage.Client(project=project_id)
                logger.info("GCS storage client initialized with ADC (project=%s)", project_id)
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


def preview_artifact_gcs_location(
    *,
    session_id: str | None,
    run_id: str | None,
    metadata: dict | None,
    preview_url: str | None = None,
) -> Optional[tuple[str, str]]:
    """GCS location for an Office HTML/PDF preview sibling, not the source file."""
    meta = metadata or {}
    url = preview_url if isinstance(preview_url, str) else meta.get("preview_url")
    if isinstance(url, str) and url:
        parsed = parse_gcs_object_url(url)
        if parsed:
            return parsed
    preview_path = meta.get("preview_path")
    bucket = meta.get("gcs_bucket")
    if (
        isinstance(preview_path, str)
        and preview_path.strip()
        and isinstance(bucket, str)
        and bucket.strip()
        and session_id
        and run_id
    ):
        return bucket.strip(), artifact_blob_name(session_id, run_id, preview_path)
    return None


def preview_media_type(preview_path: str | None, declared: str | None = None) -> str:
    explicit = (declared or "").split(";")[0].strip()
    if explicit:
        return explicit
    lower = (preview_path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if lower.endswith(".html") or lower.endswith(".htm"):
        return "text/html; charset=utf-8"
    if lower.endswith(".pdf"):
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(lower)
    return guessed or "application/octet-stream"


def parse_gcs_object_url(url: str) -> Optional[tuple[str, str]]:
    """Extract (bucket, blob) from a Google Cloud Storage HTTPS URL."""
    if not url or "storage.googleapis.com" not in url:
        return None
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if host == "storage.googleapis.com":
        if len(parts) < 2:
            return None
        return parts[0], "/".join(parts[1:])
    suffix = ".storage.googleapis.com"
    if host.endswith(suffix):
        bucket = host[: -len(suffix)]
        if not bucket or not parts:
            return None
        return bucket, "/".join(parts)
    return None


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

def download_artifact_bytes(
    *,
    bucket_name: str,
    blob_name: str,
    max_bytes: int = _CONTENT_MAX_BYTES,
) -> Optional[tuple[bytes, str]]:
    """Download a GCS blob and return (bytes, content_type).

    Returns None if the blob doesn't exist or exceeds *max_bytes*.
    """
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        blob.reload()
        if blob.size and blob.size > max_bytes:
            logger.warning(
                "Blob %s/%s is %d bytes, exceeds download limit of %d",
                bucket_name, blob_name, blob.size, max_bytes,
            )
            return None
        content = blob.download_as_bytes()
        mime = blob.content_type or mimetypes.guess_type(blob_name)[0] or "application/octet-stream"
        return content, mime
    except Exception:
        logger.exception("Failed to download blob %s/%s", bucket_name, blob_name)
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
    payload = download_artifact_bytes(
        bucket_name=bucket_name,
        blob_name=blob_name,
        max_bytes=max_bytes,
    )
    if payload is None:
        return None
    import base64

    content, mime = payload
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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

        guessed_type = mimetypes.guess_type(relative_path)[0]
        if isinstance(content, str):
            content_type = guessed_type or "text/plain"
            if content_type.startswith("text/") and "charset=" not in content_type:
                content_type = f"{content_type}; charset=utf-8"
            blob.upload_from_string(content, content_type=content_type)
        else:
            blob.upload_from_string(content, content_type=guessed_type or "application/octet-stream")

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
