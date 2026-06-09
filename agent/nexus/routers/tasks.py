# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable production task endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings
from nexus.dependencies import (
    get_history_repository,
    get_production_task_repository,
    get_task_queue,
)
from nexus.policy import evaluate_tool_policy, normalize_autonomy_mode
from nexus.production_tasks import DurableApproval, DurableTask, DurableTaskEvent, DurableTaskRun
from nexus.storage import download_artifact_as_data_uri, generate_artifact_signed_url

router = APIRouter()


class DurableTaskCreateRequest(BaseModel):
    title: str = Field(default="New task", max_length=240)
    message: str = Field(default="", max_length=20000)
    session_id: str | None = None
    connector_ids: list[str] = Field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)
    autonomy_mode: str | None = None
    budget: dict[str, Any] | None = None
    runtime_config_snapshot: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DurableTaskMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    connector_ids: list[str] = Field(default_factory=list)
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
        "session_id": run.session_id,
        "error": run.error,
        "summary": run.summary,
        "execution_payload": run.execution_payload or {},
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
    enqueue = await queue.enqueue_task_run(task_id=task.task_id, run_id=run.run_id)
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
    enqueue = await queue.enqueue_task_run(task_id=task_id, run_id=run.run_id) if payload.run else None
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
    return {"approval": _approval_payload(approval)}


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


@router.get("/api/v1/artifacts/{artifact_id}/download")
async def download_artifact_by_id(
    artifact_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repo = get_history_repository()
    artifact = await history_repo.get_artifact_for_owner(user.uid, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    # Return permanent URLs (Google Drive, data URIs) directly without GCS signing
    if artifact.url and "storage.googleapis.com" not in artifact.url:
        return {
            "artifact_id": artifact.artifact_id,
            "url": artifact.url,
            "expires_in_seconds": 900,
        }

    metadata = artifact.metadata or {}
    bucket = metadata.get("gcs_bucket")
    blob = metadata.get("gcs_blob")
    if not isinstance(bucket, str) or not isinstance(blob, str):
        raise HTTPException(status_code=409, detail="Artifact does not have durable storage metadata")
    url = generate_artifact_signed_url(bucket_name=bucket, blob_name=blob)
    if not url:
        # Signed URL failed (e.g. no SA key in local dev) — fall back to
        # downloading the blob directly and returning it as a data URI.
        url = download_artifact_as_data_uri(bucket_name=bucket, blob_name=blob)
    if not url:
        raise HTTPException(status_code=404, detail="Artifact object not found")
    return {
        "artifact_id": artifact.artifact_id,
        "url": url,
        "expires_in_seconds": 900,
    }
