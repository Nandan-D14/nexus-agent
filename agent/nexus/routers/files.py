# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Files and uploads endpoints."""

from __future__ import annotations

import re
from typing import Any
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, Response

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository, get_session_manager
from nexus.google_drive import get_google_drive_client_for_user
from nexus.models import RunArtifact
from nexus.tools.workspace import derive_workspace_path

logger = logging.getLogger(__name__)

router = APIRouter()

_SAFE_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._/ -]+$")

def _safe_workspace_relative_path(value: str) -> str:
    raw = (value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ".." in raw.split("/"):
        raise HTTPException(status_code=400, detail="relative_path must stay inside the run workspace")
    if not _SAFE_RELATIVE_PATH_RE.match(raw):
        raise HTTPException(status_code=400, detail="relative_path contains unsupported characters")
    return "/".join(part for part in raw.split("/") if part and part != ".")

def _serialize_artifact(artifact) -> RunArtifact:
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
        url=artifact.url,
        metadata=artifact.metadata or {},
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
    session = await session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Live session not found")
    if not session.current_run_id:
        raise HTTPException(status_code=400, detail="Session does not have an active run")
    await session_manager.ensure_session_ready(session_id)
    filename = _safe_workspace_relative_path(relative_path or f"sources/uploads/{file.filename or 'upload.bin'}")
    workspace_path = derive_workspace_path(session.id, session.current_run_id)
    target_path = f"{workspace_path}/{filename}"
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File uploads are limited to 20 MB")
    try:
        session.sandbox.write_binary_file(target_path, content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write file into sandbox: {exc}")
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
    return {
        "status": "uploaded",
        "path": target_path,
        "artifact": _serialize_artifact(artifact).model_dump(mode="json"),
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
    user: AuthenticatedUser = Depends(require_current_user),
):
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Live session not found")
    if not session.current_run_id:
        raise HTTPException(status_code=400, detail="Session does not have an active run")
    await session_manager.ensure_session_ready(session_id)
    filename = _safe_workspace_relative_path(relative_path)
    workspace_path = derive_workspace_path(session.id, session.current_run_id)
    target_path = f"{workspace_path}/{filename}"
    try:
        content = session.sandbox.read_binary_file(target_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"File not found or unreadable: {exc}")
    download_name = filename.rsplit("/", 1)[-1] or "download.bin"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
