# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable production task endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings
from nexus.dependencies import (
    get_history_repository,
    get_production_task_repository,
    get_task_create_limiter,
    get_task_queue,
)
from nexus.policy import evaluate_tool_policy, normalize_autonomy_mode
from nexus.production_tasks import DurableApproval, DurableTask, DurableTaskEvent, DurableTaskRun
from nexus.storage import (
    _DOWNLOAD_URL_EXPIRATION_SECONDS,
    candidate_artifact_blobs,
    download_artifact_as_data_uri,
    download_artifact_bytes,
    generate_artifact_signed_url,
    get_artifact_bucket_name,
    parse_gcs_object_url,
    preview_artifact_gcs_location,
    preview_media_type,
)

router = APIRouter()


class DurableTaskCreateRequest(BaseModel):
    title: str = Field(default="New task", max_length=240)
    message: str = Field(default="", max_length=20000)
    session_id: str | None = None
    connector_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)
    autonomy_mode: str | None = None
    budget: dict[str, Any] | None = None
    runtime_config_snapshot: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DurableTaskMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    connector_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)
    runtime_config_snapshot: dict[str, Any] = Field(default_factory=dict)
    autonomy_mode: str | None = None
    budget: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    run: bool = True


class ApprovalResolveRequest(BaseModel):
    approved: bool


class PolicyPreviewRequest(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    autonomy_mode: str | None = None
    untrusted_input_in_scope: bool = False


def _task_payload(task: DurableTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "owner_id": task.owner_id,
        "title": task.title,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "autonomy_mode": task.autonomy_mode,
        "session_id": task.session_id,
        "current_run_id": task.current_run_id,
        "cancel_requested": task.cancel_requested,
        "budget": task.budget or {},
        "sandbox_state": task.sandbox_state or {},
        "metadata": task.metadata or {},
    }


def _run_payload(run: DurableTaskRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "task_id": run.task_id,
        "owner_id": run.owner_id,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "lease_owner": run.lease_owner,
        "lease_expires_at": run.lease_expires_at.isoformat() if run.lease_expires_at else None,
        "attempt": run.attempt,
        "claim_generation": run.claim_generation,
        "session_id": run.session_id,
        "error": run.error,
        "summary": run.summary,
        "execution_payload": run.execution_payload or {},
        "checkpoint": run.checkpoint or {},
        "verification": run.verification or {},
        "final_response": run.final_response,
    }


def _event_payload(event: DurableTaskEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "task_id": event.task_id,
        "run_id": event.run_id,
        "type": event.event_type,
        "created_at": event.created_at.isoformat(),
        "payload": event.payload,
        "seq": event.seq,
    }


def _approval_payload(approval: DurableApproval) -> dict[str, Any]:
    return {
        "approval_id": approval.approval_id,
        "task_id": approval.task_id,
        "status": approval.status,
        "description": approval.description,
        "risk": approval.risk,
        "approved": approval.approved,
        "created_at": approval.created_at.isoformat(),
        "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        "metadata": approval.metadata or {},
    }


@router.post("/api/v1/tasks")
async def create_durable_task(
    payload: DurableTaskCreateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not get_task_create_limiter().check(user.uid):
        raise HTTPException(status_code=429, detail="Too many task creates; slow down.")
    repo = get_production_task_repository()
    queue = get_task_queue()
    task = await repo.create_task(
        owner_id=user.uid,
        title=payload.title or payload.message[:120] or "New task",
        input_text=payload.message,
        autonomy_mode=normalize_autonomy_mode(payload.autonomy_mode),
        session_id=payload.session_id,
        budget=payload.budget,
        metadata=payload.metadata,
    )
    run = await repo.create_run(
        task_id=task.task_id,
        owner_id=user.uid,
        session_id=payload.session_id,
        input_text=payload.message,
        connector_ids=payload.connector_ids,
        tool_ids=payload.tool_ids,
        uploaded_files=payload.uploaded_files,
        runtime_config_snapshot=payload.runtime_config_snapshot,
        autonomy_mode=payload.autonomy_mode,
        budget=payload.budget,
        metadata=payload.metadata,
    )
    await repo.append_event(
        task_id=task.task_id,
        owner_id=user.uid,
        run_id=run.run_id,
        event_type="task_created",
        payload={
            "title": task.title,
            "autonomy_mode": task.autonomy_mode,
            "session_id": payload.session_id,
        },
    )
    enqueue_kwargs = {"task_id": task.task_id, "run_id": run.run_id}
    if run.claim_token:
        enqueue_kwargs["claim_token"] = run.claim_token
    enqueue = await queue.enqueue_task_run(**enqueue_kwargs)
    return {
        "task": _task_payload(task),
        "run": _run_payload(run),
        "queue": enqueue.__dict__,
    }


@router.get("/api/v1/tasks/{task_id}")
async def get_durable_task(task_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    repo = get_production_task_repository()
    task = await repo.get_task(task_id)
    if not task or task.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": _task_payload(task)}


@router.get("/api/v1/tasks/{task_id}/events")
async def list_durable_task_events(
    task_id: str,
    after_event_id: str | None = Query(default=None),
    after_seq: int | None = Query(default=None, ge=0),
    run_id: str | None = Query(default=None),
    limit: int = Query(default=settings.task_event_replay_limit, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Replay durable task events.

    Clients should prefer ``after_seq`` (the last ``seq`` they received) for
    reconnect/replay because seq is monotonic per task. ``after_event_id`` is
    kept as a fallback for older clients and legacy events written before seq
    numbers existed.
    """
    repo = get_production_task_repository()
    task = await repo.get_task(task_id)
    if not task or task.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Task not found")
    events = await repo.list_events(
        task_id=task_id,
        owner_id=user.uid,
        after_event_id=after_event_id,
        after_seq=after_seq,
        run_id=run_id,
        limit=limit,
    )
    payloads = [_event_payload(event) for event in events]
    last_seq = max((event.seq for event in events), default=after_seq or 0)
    return {
        "events": payloads,
        "last_seq": last_seq,
        "has_more": len(payloads) >= limit,
    }


@router.post("/api/v1/tasks/{task_id}/messages")
async def append_durable_task_message(
    task_id: str,
    payload: DurableTaskMessageRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    repo = get_production_task_repository()
    queue = get_task_queue()
    task = await repo.get_task(task_id)
    if not task or task.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Task not found")
    run = await repo.create_run(
        task_id=task_id,
        owner_id=user.uid,
        session_id=task.session_id,
        input_text=payload.message,
        connector_ids=payload.connector_ids,
        tool_ids=payload.tool_ids,
        uploaded_files=payload.uploaded_files,
        runtime_config_snapshot=payload.runtime_config_snapshot,
        autonomy_mode=payload.autonomy_mode,
        budget=payload.budget,
        metadata=payload.metadata,
    )
    event = await repo.append_event(
        task_id=task_id,
        owner_id=user.uid,
        run_id=run.run_id,
        event_type="user_message",
        payload={"text": payload.message},
    )
    enqueue = (
        await queue.enqueue_task_run(
            **{
                "task_id": task_id,
                "run_id": run.run_id,
                **(
                    {"claim_token": run.claim_token}
                    if run.claim_token
                    else {}
                ),
            }
        )
        if payload.run
        else None
    )
    return {
        "event": _event_payload(event),
        "run": _run_payload(run),
        "queue": enqueue.__dict__ if enqueue else None,
    }


@router.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_durable_task(task_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    repo = get_production_task_repository()
    cancelled = await repo.request_cancel(task_id=task_id, owner_id=user.uid)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "cancelling"}


@router.post("/api/v1/tasks/{task_id}/approvals/{approval_id}")
async def resolve_durable_task_approval(
    task_id: str,
    approval_id: str,
    payload: ApprovalResolveRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    repo = get_production_task_repository()
    approval = await repo.resolve_approval(
        task_id=task_id,
        approval_id=approval_id,
        owner_id=user.uid,
        approved=payload.approved,
    )
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    enqueue_payload = None
    metadata = approval.metadata or {}
    run_id = str(metadata.get("run_id") or "")
    if run_id:
        run = await repo.get_run(
            task_id=task_id,
            run_id=run_id,
            owner_id=user.uid,
        )
        if run and run.status in {"waiting_approval", "paused"}:
            checkpoint = dict(run.checkpoint or {})
            checkpoint["approval_resolution"] = {
                "approval_id": approval.approval_id,
                "approved": payload.approved,
                "action_hash": metadata.get("action_hash"),
                "tool": metadata.get("tool"),
                "canonical_args": metadata.get("canonical_args") or {},
                "args_preview": metadata.get("args_preview") or {},
            }
            await repo.save_checkpoint(
                task_id=task_id,
                run_id=run_id,
                owner_id=user.uid,
                checkpoint=checkpoint,
            )
            requeued = await repo.requeue_run(
                task_id=task_id,
                run_id=run_id,
                reason="Approval resolved; resume exact blocked action.",
                expected_generation=run.claim_generation,
            )
            if requeued is not None:
                enqueue = await get_task_queue().enqueue_task_run(
                    task_id=task_id,
                    run_id=run_id,
                    claim_token=requeued.claim_token,
                )
                enqueue_payload = enqueue.__dict__
    return {
        "approval": _approval_payload(approval),
        "queue": enqueue_payload,
    }


@router.get("/api/v1/tasks/{task_id}/approvals")
async def list_durable_task_approvals(
    task_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user: AuthenticatedUser = Depends(require_current_user),
):
    repo = get_production_task_repository()
    task = await repo.get_task(task_id)
    if not task or task.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Task not found")
    approvals = await repo.list_approvals(
        task_id=task_id,
        owner_id=user.uid,
        status=status,
        limit=limit,
    )
    return {"approvals": [_approval_payload(item) for item in approvals]}


@router.post("/api/v1/policy/preview")
async def preview_policy(
    payload: PolicyPreviewRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    decision = evaluate_tool_policy(
        payload.tool_name,
        payload.args,
        autonomy_mode=payload.autonomy_mode,
        untrusted_input_in_scope=payload.untrusted_input_in_scope,
    )
    return {
        "action": decision.action,
        "risk": decision.risk,
        "reason": decision.reason,
        "user_id": user.uid,
    }


def _optional_query_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _artifact_gcs_location(artifact) -> tuple[str, str] | None:
    """Primary GCS location (stored blob or legacy GCS URL)."""
    metadata = artifact.metadata or {}
    bucket = metadata.get("gcs_bucket")
    blob = metadata.get("gcs_blob")
    if isinstance(bucket, str) and bucket.strip() and isinstance(blob, str) and blob.strip():
        return bucket.strip(), blob.strip()
    return parse_gcs_object_url(getattr(artifact, "url", None) or "")


def _artifact_gcs_candidates(artifact) -> list[tuple[str, str]]:
    """All (bucket, blob) candidates: stored > immutable > legacy > GCS URL.

    Guarantees pre-immutable artifacts (same filename overwrites) still resolve
    via legacy path, while new immutable blobs are tried first. Legacy signed
    URLs may point at another env bucket - honor their bucket explicitly.
    """
    from nexus.storage import _clean_relative_path

    metadata = dict(artifact.metadata or {}) if isinstance(getattr(artifact, "metadata", None), dict) else {}
    _sid = getattr(artifact, "session_id", None)
    _rid = getattr(artifact, "run_id", None)
    _aid = getattr(artifact, "artifact_id", None)
    session_id = _sid.strip() if isinstance(_sid, str) and _sid.strip() else None
    run_id = _rid.strip() if isinstance(_rid, str) and _rid.strip() else None
    artifact_id = _aid.strip() if isinstance(_aid, str) and _aid.strip() else None
    # Prefer explicit relative_path; fall back to filename from path/title.
    relative = metadata.get("relative_path")
    if not isinstance(relative, str) or not relative.strip():
        raw_path = (getattr(artifact, "path", None) or "").replace("\\", "/")
        candidate = raw_path.split("/")[-1] if raw_path else ""
        if not candidate:
            candidate = str(getattr(artifact, "title", None) or "")
        # If path was absolute sandbox path, keep outputs/... tail.
        if "/outputs/" in raw_path:
            candidate = "outputs/" + raw_path.split("/outputs/")[-1]
        elif "/uploads/" in raw_path:
            candidate = "uploads/" + raw_path.split("/uploads/")[-1]
        relative = candidate
    try:
        relative = _clean_relative_path(relative or "")
    except Exception:
        relative = ""
    bucket = metadata.get("gcs_bucket")
    bucket_name = bucket.strip() if isinstance(bucket, str) and bucket.strip() else get_artifact_bucket_name()
    blobs = candidate_artifact_blobs(session_id, run_id, relative or None, artifact_id, metadata)
    out: list[tuple[str, str]] = [(bucket_name, b) for b in blobs]
    # Also honor a parsable legacy GCS URL (may be another bucket).
    parsed = parse_gcs_object_url(getattr(artifact, "url", None) or "")
    if parsed and all(blob != parsed[1] or bkt != parsed[0] for bkt, blob in out):
        out.append(parsed)
    return out


def _download_first_candidate(
    candidates: list[tuple[str, str]],
) -> tuple[bytes, str, str] | None:
    """Try candidates via download_artifact_bytes (mock-friendly)."""
    for bucket_name, blob_name in candidates:
        payload = download_artifact_bytes(bucket_name=bucket_name, blob_name=blob_name)
        if payload is not None:
            content, mime = payload
            return content, mime, blob_name
    return None


def _content_disposition_filename(artifact, blob_name: str | None = None) -> str:
    raw = (
        getattr(artifact, "title", None)
        or (blob_name.split("/")[-1] if blob_name else "")
        or "artifact"
    )
    cleaned = "".join(ch for ch in str(raw) if ch not in {"\r", "\n", '"'}).strip()
    return cleaned[:180] or "artifact"


@router.get("/api/v1/artifacts/{artifact_id}/download")
async def download_artifact_by_id(
    artifact_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    session_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
):
    history_repo = get_history_repository()
    artifact = await history_repo.get_artifact_for_owner(
        user.uid,
        artifact_id,
        session_id=session_id,
        run_id=run_id,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_DOC_NOT_FOUND", "message": "Artifact not found. It may predate durable storage."})

    # Return permanent URLs (Google Drive, data URIs) directly without GCS signing
    if artifact.url and "storage.googleapis.com" not in artifact.url:
        return {
            "artifact_id": artifact.artifact_id,
            "url": artifact.url,
            "expires_in_seconds": _DOWNLOAD_URL_EXPIRATION_SECONDS,
            "durable": False,
        }

    for bucket_name, blob in _artifact_gcs_candidates(artifact):
        url = generate_artifact_signed_url(bucket_name=bucket_name, blob_name=blob)
        if not url:
            # Signed URL failed — fall back to downloading the blob directly
            url = download_artifact_as_data_uri(bucket_name=bucket_name, blob_name=blob)
        if url:
            return {
                "artifact_id": artifact.artifact_id,
                "url": url,
                "expires_in_seconds": _DOWNLOAD_URL_EXPIRATION_SECONDS,
                "durable": True,
            }

    # Artifact has no durable storage — it was created before GCS was fixed,
    # or the upload failed silently. The sandbox it was created in is likely gone.
    # Return the original URL if present (even if expired), or a clear error.
    if artifact.url:
        return {
            "artifact_id": artifact.artifact_id,
            "url": artifact.url,
            "expires_in_seconds": 0,
            "durable": False,
        }

    raise HTTPException(
        status_code=410,
        detail={"code": "ARTIFACT_BLOB_MISSING", "message": "Original file is no longer available - the sandbox expired before durable storage. Please regenerate."},
    )


@router.get("/api/v1/artifacts/{artifact_id}/content")
async def download_artifact_content(
    artifact_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    session_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    sibling: str | None = Query(default=None),
):
    """Same-origin byte proxy so the browser never fetch()es GCS (no CORS).

    Durable-first: serves exact original bytes from GCS for all sessions,
    independent of live sandbox state. Sandboxes are ephemeral execution only.
    """
    session_id = _optional_query_text(session_id)
    run_id = _optional_query_text(run_id)
    sibling = _optional_query_text(sibling)
    history_repo = get_history_repository()
    artifact = await history_repo.get_artifact_for_owner(
        user.uid,
        artifact_id,
        session_id=session_id,
        run_id=run_id,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_DOC_NOT_FOUND", "message": "Artifact not found."})

    metadata = artifact.metadata or {}
    want_preview = (sibling or "").lower() == "preview"
    if want_preview:
        location = preview_artifact_gcs_location(
            session_id=getattr(artifact, "session_id", None) or session_id,
            run_id=getattr(artifact, "run_id", None) or run_id,
            metadata=metadata,
            artifact_id=getattr(artifact, "artifact_id", None),
        )
        if location:
            bucket, blob = location
            payload = download_artifact_bytes(bucket_name=bucket, blob_name=blob)
            if payload is not None:
                content, mime = payload
                filename = _content_disposition_filename(artifact, blob)
                mime = preview_media_type(
                    str(metadata.get("preview_path") or blob),
                    str(metadata.get("preview_content_type") or ""),
                )
                preview_name = str(metadata.get("preview_path") or "").replace("\\", "/").rsplit("/", 1)[-1]
                if preview_name:
                    filename = preview_name
                return Response(
                    content=content,
                    media_type=mime,
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}"',
                        "Cache-Control": "private, max-age=60",
                        "ETag": f'"{artifact.artifact_id}-preview"',
                    },
                )
        raise HTTPException(
            status_code=404,
            detail={"code": "ARTIFACT_PREVIEW_MISSING", "message": "Preview not available. Download the original file."},
        )

    hit = _download_first_candidate(_artifact_gcs_candidates(artifact))
    if hit is not None:
        content, mime, blob = hit
        filename = _content_disposition_filename(artifact, blob)
        declared = str(metadata.get("content_type") or "").strip()
        if declared:
            mime = declared
        return Response(
            content=content,
            media_type=mime,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "private, max-age=60",
                "ETag": f'"{artifact.artifact_id}"',
            },
        )

    raise HTTPException(
        status_code=410,
        detail={"code": "ARTIFACT_BLOB_MISSING", "message": "Original file is no longer available - the sandbox expired before durable storage. Please regenerate."},
    )

