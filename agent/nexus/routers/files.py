# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Files and uploads endpoints."""

from __future__ import annotations

import mimetypes
import re
from typing import Any
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, Response

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository, get_session_manager
from nexus.google_drive import get_google_drive_client_for_user
from nexus.models import RunArtifact
from nexus.storage import generate_artifact_signed_url
from nexus.tools.workspace import derive_workspace_path

logger = logging.getLogger(__name__)

router = APIRouter()

_UNSAFE_PATH_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._ -]+")

_OFFICE_MIME = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".py": "text/x-python",
    ".ts": "text/typescript",
    ".tsx": "text/tsx",
    ".js": "text/javascript",
    ".jsx": "text/javascript",
    ".json": "application/json",
    ".css": "text/css",
    ".go": "text/x-go",
    ".rs": "text/rust",
    ".java": "text/x-java-source",
    ".yml": "text/yaml",
    ".yaml": "text/yaml",
    ".toml": "application/toml",
    ".sh": "text/x-sh",
    ".sql": "application/sql",
    ".xml": "application/xml",
}


def _mime_for_filename(name: str) -> str:
    suffix = ""
    if "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()
    if suffix in _OFFICE_MIME:
        return _OFFICE_MIME[suffix]
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def _sanitize_relative_path_segment(part: str) -> str:
    cleaned = _UNSAFE_PATH_SEGMENT_RE.sub("_", (part or "").strip()).strip(" .")
    return cleaned[:180]


def _safe_workspace_relative_path(value: str, session_id: str | None = None, run_id: str | None = None) -> str:
    raw = (value or "").strip().replace("\\", "/")
    
    # Strip workspace root prefixes if they are present
    if session_id:
        from nexus.tools.workspace import derive_workspace_path, derive_session_workspace_path
        if run_id:
            run_root = derive_workspace_path(session_id, run_id).replace("\\", "/").rstrip("/")
            if raw.startswith(run_root):
                raw = raw[len(run_root):].lstrip("/")
        session_root = derive_session_workspace_path(session_id).replace("\\", "/").rstrip("/")
        if raw.startswith(session_root):
            raw = raw[len(session_root):].lstrip("/")
        # The UI often sends `sessionId/runId/outputs/file.xlsx` after
        # splitting on `/Workspaces/`. That is still a workspace-absolute
        # path; joining it onto the run root looks in a nested folder that
        # does not exist, so the preview 404s.
        if raw.startswith(f"{session_id}/"):
            raw = raw[len(session_id) + 1 :]
        if run_id and raw.startswith(f"{run_id}/"):
            raw = raw[len(run_id) + 1 :]


    if not raw or raw.startswith("/") or ".." in raw.split("/"):
        raise HTTPException(status_code=400, detail="relative_path must stay inside the run workspace")
    parts = [_sanitize_relative_path_segment(part) for part in raw.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise HTTPException(status_code=400, detail="relative_path must stay inside the run workspace")
    if not all(parts):
        raise HTTPException(status_code=400, detail="relative_path contains unsupported characters")
    return "/".join(parts)


def _serialize_artifact(artifact) -> RunArtifact:
    url = artifact.url
    metadata = artifact.metadata or {}
    
    # Refresh expired GCS signed URLs. Google Drive URLs are permanent.
    if url and "drive.google.com" not in url and "storage.googleapis.com" in url:
        gcs_bucket = metadata.get("gcs_bucket")
        gcs_blob = metadata.get("gcs_blob")
        if gcs_bucket and gcs_blob:
            fresh_url = generate_artifact_signed_url(bucket_name=gcs_bucket, blob_name=gcs_blob)
            if fresh_url:
                url = fresh_url

    return RunArtifact(
        artifact_id=artifact.artifact_id,
        run_id=artifact.run_id,
        session_id=artifact.session_id,
        task_id=artifact.task_id,
        kind=artifact.kind,
        title=artifact.title,
        preview=artifact.preview,
        created_at=artifact.created_at,
        source_step_id=artifact.source_step_id,
        path=artifact.path,
        url=url,
        metadata=metadata,
    )

async def _mirror_upload_to_google_drive(
    *,
    user_id: str,
    session_id: str,
    filename: str,
    content: bytes,
    mime_type: str | None,
) -> dict[str, Any]:
    history_repository = get_history_repository()
    client = await get_google_drive_client_for_user(history_repository, user_id)
    if client is None:
        return {"status": "skipped"}
    folder = await client.ensure_folder_path(["CoComputer", "Sessions", session_id, "Uploads"])
    uploaded = await client.upload_bytes(
        filename=filename,
        content=content,
        mime_type=mime_type or "application/octet-stream",
        parent_id=folder["folder_id"],
    )
    return {
        "status": "uploaded",
        "drive_file_id": uploaded.get("id"),
        "web_view_link": uploaded.get("webViewLink"),
        "folder_path": folder["path"],
        "folder_id": folder["folder_id"],
    }


async def _ensure_session_run(session, history_repository) -> str:
    if session.current_run_id:
        return session.current_run_id
    stored_run = None
    try:
        stored = await history_repository.get_session(session.id)
        stored_run = getattr(stored, "current_run_id", None) if stored else None
    except Exception:
        logger.warning("Could not restore current run for session %s", session.id, exc_info=True)
    if isinstance(stored_run, str) and stored_run:
        session.current_run_id = stored_run
        return stored_run
    run = await history_repository.create_run(
        session_id=session.id,
        owner_id=session.owner_id,
        title="Uploads",
    )
    session.current_run_id = run.run_id
    session.run_status = getattr(run, "status", session.run_status)
    return run.run_id


@router.post("/api/v1/sessions/{session_id}/files/upload")
async def upload_session_file(
    session_id: str,
    file: UploadFile = File(...),
    relative_path: str | None = Form(default=None),
    mirror_to_drive: bool = Form(default=True),
    user: AuthenticatedUser = Depends(require_current_user),
):
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    session = session_manager.get_live_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Live session not found. Keep the session tab open and try again.")
    try:
        await _ensure_session_run(session, history_repository)
    except Exception:
        logger.exception("Failed to ensure a run for session upload %s", session.id)
        raise HTTPException(status_code=400, detail="Session does not have an active run")
    try:
        await session_manager.ensure_session_ready(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Live session not found. Keep the session tab open and try again.")
    except Exception:
        logger.exception("Failed to prepare sandbox for session upload %s", session.id)
        raise HTTPException(status_code=503, detail="Workspace is still starting. Try again in a moment.")
    filename = _safe_workspace_relative_path(
        relative_path or f"sources/uploads/{file.filename or 'upload.bin'}",
        session_id=session.id,
        run_id=session.current_run_id,
    )
    workspace_path = derive_workspace_path(session.id, session.current_run_id)
    target_path = f"{workspace_path}/{filename}"
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File uploads are limited to 20 MB")
    try:
        session.sandbox.write_binary_file(target_path, content)
    except Exception as exc:
        logger.exception(
            "Failed to write upload into sandbox for session %s (%d bytes, path=%s)",
            session.id,
            len(content),
            target_path,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to write file into the workspace. Reconnect the session and try again.",
        ) from exc
    drive_result: dict[str, Any] = {"status": "skipped"}
    if mirror_to_drive:
        try:
            drive_result = await _mirror_upload_to_google_drive(
                user_id=user.uid,
                session_id=session.id,
                filename=file.filename or filename.rsplit("/", 1)[-1] or "upload.bin",
                content=content,
                mime_type=file.content_type,
            )
        except Exception as exc:
            logger.warning("Drive mirror failed for session upload %s: %s", session.id, exc, exc_info=True)
            drive_result = {"status": "error", "error": str(exc)}
    artifact_metadata = {
        "relative_path": filename,
        "size": len(content),
        "content_type": file.content_type,
        "drive_status": drive_result.get("status", "skipped"),
    }
    if drive_result.get("drive_file_id"):
        artifact_metadata["drive_file_id"] = drive_result["drive_file_id"]
    if drive_result.get("web_view_link"):
        artifact_metadata["drive_web_view_link"] = drive_result["web_view_link"]
    if drive_result.get("folder_path"):
        artifact_metadata["drive_folder_path"] = drive_result["folder_path"]
    if drive_result.get("error"):
        artifact_metadata["drive_error"] = drive_result["error"]
    artifact_payload: dict[str, Any]
    try:
        artifact = await history_repository.create_artifact(
            session_id=session.id,
            run_id=session.current_run_id,
            kind="uploaded_file",
            title=file.filename or filename,
            preview=f"Uploaded {file.filename or filename} to {target_path}",
            path=target_path,
            url=drive_result.get("web_view_link"),
            metadata=artifact_metadata,
        )
        artifact_payload = _serialize_artifact(artifact).model_dump(mode="json")
    except Exception:
        logger.exception("Failed to record upload artifact for session %s", session.id)
        artifact_payload = {
            "artifact_id": "",
            "run_id": session.current_run_id,
            "session_id": session.id,
            "task_id": session.task_id or session.id,
            "kind": "uploaded_file",
            "title": file.filename or filename,
            "preview": f"Uploaded {file.filename or filename} to {target_path}",
            "created_at": None,
            "source_step_id": None,
            "path": target_path,
            "url": drive_result.get("web_view_link"),
            "metadata": artifact_metadata,
        }
    return {
        "status": "uploaded",
        "path": target_path,
        "artifact": artifact_payload,
        "drive_status": drive_result.get("status", "skipped"),
        "drive_file_id": drive_result.get("drive_file_id"),
        "drive_web_view_link": drive_result.get("web_view_link"),
        "drive_folder_path": drive_result.get("folder_path"),
        "drive_error": drive_result.get("error"),
    }

@router.get("/api/v1/sessions/{session_id}/files/download")
async def download_session_file(
    session_id: str,
    relative_path: str = Query(...),
    run_id: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Live sandbox file access (ephemeral execution only).

    For permanent access to delivered files (xlsx/pdf/docx/pptx/html/...) use
    GET /api/v1/artifacts/{artifact_id}/content which serves the exact original
    from durable GCS for all sessions, even after the sandbox is paused.
    """
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(
            status_code=404,
            detail={"code": "LIVE_SESSION_NOT_FOUND", "message": "Live session not found. Use /api/v1/artifacts/{id}/content for durable files."},
        )
    active_run_id = run_id or session.current_run_id
    if not active_run_id:
        raise HTTPException(status_code=400, detail={"code": "NO_ACTIVE_RUN", "message": "Session does not have an active run"})

    # Revive a paused/stale sandbox before declaring it gone. The previous
    # fail-fast 410 ran *before* ensure_session_ready, so a live session whose
    # VM had been paused (or whose in-memory handle was empty after a
    # reconnect) could never serve a file that was still on disk.
    await session_manager.ensure_session_ready(session_id)
    session = await session_manager.get_session(session_id) or session
    if not session.sandbox or not session.sandbox.is_alive:
        raise HTTPException(
            status_code=410,
            detail={"code": "SANDBOX_EPHEMERAL", "message": "Sandbox is paused/expired. Open the file from Library or chat artifact (durable GCS copy)."},
        )

    filename = _safe_workspace_relative_path(
        relative_path, session_id=session.id, run_id=active_run_id
    )
    workspace_path = derive_workspace_path(session.id, active_run_id)
    target_path = f"{workspace_path}/{filename}"
    try:
        content = session.sandbox.read_binary_file(target_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File not found or unreadable: {exc}")
    download_name = filename.rsplit("/", 1)[-1] or "download.bin"
    return Response(
        content=content,
        media_type=_mime_for_filename(download_name),
        headers={"Content-Disposition": f'inline; filename="{download_name}"'},
    )


@router.get("/api/v1/sessions/{session_id}/files/tree")
async def list_session_file_tree(
    session_id: str,
    relative_path: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Return a recursive listing of the live run workspace (or a subdirectory)."""
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Live session not found")
    if not session.current_run_id:
        raise HTTPException(status_code=400, detail="Session does not have an active run")
    if not session.sandbox or not session.sandbox.is_alive:
        raise HTTPException(
            status_code=410,
            detail="Sandbox container is not active. Workspace files cannot be listed.",
        )

    await session_manager.ensure_session_ready(session_id)
    workspace_path = derive_workspace_path(session.id, session.current_run_id)
    sub_path = ""
    if relative_path:
        sub_path = _safe_workspace_relative_path(
            relative_path,
            session_id=session.id,
            run_id=session.current_run_id,
        )
    target_path = f"{workspace_path}/{sub_path}" if sub_path else workspace_path
    try:
        entries = session.sandbox.list_tree(target_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list workspace files: {exc}")

    # When listing a subdirectory, prefix relative_path so download URLs stay workspace-relative.
    if sub_path:
        prefixed = []
        for entry in entries:
            rel = str(entry.get("relative_path") or "")
            prefixed.append(
                {
                    **entry,
                    "relative_path": f"{sub_path}/{rel}" if rel else sub_path,
                }
            )
        entries = prefixed

    return {
        "workspace_path": workspace_path,
        "relative_path": sub_path,
        "entries": entries,
    }


@router.get("/api/v1/sessions/{session_id}/files/zip")
async def download_session_workspace_zip(
    session_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Download the run workspace as a gzip tar, skipping bulky dependency dirs."""
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Live session not found")
    if not session.current_run_id:
        raise HTTPException(status_code=400, detail="Session does not have an active run")
    if not session.sandbox or not session.sandbox.is_alive:
        raise HTTPException(
            status_code=410,
            detail="Sandbox container is not active. Workspace cannot be archived.",
        )

    await session_manager.ensure_session_ready(session_id)
    workspace_path = derive_workspace_path(session.id, session.current_run_id)
    try:
        content = session.sandbox.archive_tree(workspace_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to archive workspace: {exc}")
    download_name = f"workspace-{session.id[:12]}.tgz"
    return Response(
        content=content,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
