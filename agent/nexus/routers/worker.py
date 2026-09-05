# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Internal worker endpoints for Cloud Tasks."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from nexus.config import settings
from nexus.task_worker import task_worker

router = APIRouter()


class WorkerRunRequest(BaseModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    claim_token: str | None = None


def _validate_worker_token(token: str | None) -> None:
    if not settings.task_worker_auth_token:
        raise HTTPException(status_code=503, detail="Worker token is not configured")
    if token != settings.task_worker_auth_token:
        raise HTTPException(status_code=403, detail="Invalid worker token")


@router.post("/internal/tasks/run")
async def run_task_from_queue(
    payload: WorkerRunRequest,
    x_worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
):
    if not settings.task_worker_enabled:
        raise HTTPException(status_code=503, detail="Durable task worker is disabled")
    _validate_worker_token(x_worker_token)
    result = await task_worker.run_once(
        task_id=payload.task_id,
        run_id=payload.run_id,
        claim_token=payload.claim_token,
    )
    return {"status": result.status, "summary": result.summary}


@router.post("/internal/schedules/tick")
async def tick_schedules(
    x_worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
):
    if not settings.task_worker_enabled:
        raise HTTPException(status_code=503, detail="Durable task worker is disabled")
    _validate_worker_token(x_worker_token)
    from nexus.schedule_dispatch import tick_due_schedules

    return await tick_due_schedules()
