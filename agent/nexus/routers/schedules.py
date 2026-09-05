# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""CRUD endpoints for scheduled agent jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings
from nexus.dependencies import get_schedule_store
from nexus.repositories.schedule_store import ScheduleStore, build_schedule_from_input
from nexus.schedules import (
    compute_next_run,
    firing_payload,
    schedule_payload,
)
from nexus.production_tasks import utcnow

router = APIRouter()


class ScheduleCreateRequest(BaseModel):
    title: str = Field(default="", max_length=240)
    prompt: str = Field(min_length=1, max_length=20000)
    timezone: str = Field(default="UTC", max_length=80)
    freq: str = Field(default="daily", max_length=32)
    time_of_day: str = Field(default="09:00", max_length=8)
    days_of_week: list[int] = Field(default_factory=list)
    once_at: str | None = None
    day_of_month: int = Field(default=1, ge=1, le=31)
    run_mode: str = Field(default="new_task", max_length=32)
    continue_task_id: str | None = None
    connector_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)
    autonomy_mode: str | None = None
    skip_confirmations: bool = False
    allowed_unattended_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScheduleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    prompt: str | None = Field(default=None, max_length=20000)
    timezone: str | None = Field(default=None, max_length=80)
    freq: str | None = Field(default=None, max_length=32)
    time_of_day: str | None = Field(default=None, max_length=8)
    days_of_week: list[int] | None = None
    once_at: str | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    run_mode: str | None = Field(default=None, max_length=32)
    continue_task_id: str | None = None
    connector_ids: list[str] | None = None
    tool_ids: list[str] | None = None
    autonomy_mode: str | None = None
    skip_confirmations: bool | None = None
    allowed_unattended_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None


@router.post("/api/v1/schedules")
async def create_schedule(
    payload: ScheduleCreateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    active = await store.count_active(user.uid)
    if active >= settings.max_active_schedules:
        raise HTTPException(
            status_code=400,
            detail=f"Active schedule limit reached ({settings.max_active_schedules}).",
        )
    try:
        schedule = build_schedule_from_input(
            owner_id=user.uid,
            title=payload.title,
            prompt=payload.prompt,
            timezone_name=payload.timezone,
            freq=payload.freq,
            time_of_day=payload.time_of_day,
            days_of_week=payload.days_of_week,
            once_at=payload.once_at,
            day_of_month=payload.day_of_month,
            run_mode=payload.run_mode,
            continue_task_id=payload.continue_task_id,
            connector_ids=payload.connector_ids,
            tool_ids=payload.tool_ids,
            autonomy_mode=payload.autonomy_mode,
            skip_confirmations=payload.skip_confirmations,
            allowed_unattended_tools=payload.allowed_unattended_tools,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    created = await store.create_schedule(schedule)
    return {"schedule": schedule_payload(created)}


@router.get("/api/v1/schedules")
async def list_schedules(
    limit: int = Query(default=100, ge=1, le=200),
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    rows = await store.list_schedules(user.uid, limit=limit)
    return {"schedules": [schedule_payload(item) for item in rows]}


@router.get("/api/v1/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule_payload(schedule)}


@router.patch("/api/v1/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    try:
        updated = build_schedule_from_input(
            owner_id=user.uid,
            title=payload.title if payload.title is not None else schedule.title,
            prompt=payload.prompt if payload.prompt is not None else schedule.prompt,
            timezone_name=payload.timezone if payload.timezone is not None else schedule.timezone,
            freq=payload.freq if payload.freq is not None else schedule.freq,
            time_of_day=payload.time_of_day if payload.time_of_day is not None else schedule.time_of_day,
            days_of_week=payload.days_of_week if payload.days_of_week is not None else schedule.days_of_week,
            once_at=payload.once_at if payload.once_at is not None else schedule.once_at,
            day_of_month=payload.day_of_month if payload.day_of_month is not None else schedule.day_of_month,
            run_mode=payload.run_mode if payload.run_mode is not None else schedule.run_mode,
            continue_task_id=(
                payload.continue_task_id
                if payload.continue_task_id is not None
                else schedule.continue_task_id
            ),
            connector_ids=payload.connector_ids if payload.connector_ids is not None else schedule.connector_ids,
            tool_ids=payload.tool_ids if payload.tool_ids is not None else schedule.tool_ids,
            autonomy_mode=(
                payload.autonomy_mode
                if payload.autonomy_mode is not None
                else schedule.autonomy_mode
            ),
            skip_confirmations=(
                payload.skip_confirmations
                if payload.skip_confirmations is not None
                else schedule.skip_confirmations
            ),
            allowed_unattended_tools=(
                payload.allowed_unattended_tools
                if payload.allowed_unattended_tools is not None
                else schedule.allowed_unattended_tools
            ),
            status=schedule.status,
            schedule_id=schedule.schedule_id,
            metadata=payload.metadata if payload.metadata is not None else schedule.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    updated.created_at = schedule.created_at
    updated.last_run_at = schedule.last_run_at
    updated.current_run_id = schedule.current_run_id
    updated.last_task_id = schedule.last_task_id
    updated.last_session_id = schedule.last_session_id
    if updated.status == "paused":
        updated.next_run_at = schedule.next_run_at
    saved = await store.save_schedule(updated)
    return {"schedule": schedule_payload(saved)}


@router.delete("/api/v1/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await store.delete_schedule(schedule_id)
    return {"status": "deleted"}


@router.post("/api/v1/schedules/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status = "paused"
    saved = await store.save_schedule(schedule)
    return {"schedule": schedule_payload(saved)}


@router.post("/api/v1/schedules/{schedule_id}/resume")
async def resume_schedule(
    schedule_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.status = "active"
    nxt = compute_next_run(schedule, after=utcnow())
    if nxt is None:
        raise HTTPException(status_code=400, detail="Schedule has no upcoming run time")
    schedule.next_run_at = nxt
    saved = await store.save_schedule(schedule)
    return {"schedule": schedule_payload(saved)}


@router.post("/api/v1/schedules/{schedule_id}/run-now")
async def run_schedule_now(
    schedule_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    from nexus.schedule_dispatch import fire_schedule

    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    result = await fire_schedule(schedule_id, force=True)
    if result.status == "error":
        raise HTTPException(status_code=409, detail=result.reason or "Schedule could not run")
    refreshed = await store.get_schedule(schedule_id)
    return {
        "result": result.as_dict(),
        "schedule": schedule_payload(refreshed) if refreshed else None,
    }


@router.get("/api/v1/schedules/{schedule_id}/firings")
async def list_schedule_firings(
    schedule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthenticatedUser = Depends(require_current_user),
    store: ScheduleStore = Depends(get_schedule_store),
):
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    rows = await store.list_firings(schedule_id, limit=limit)
    return {"firings": [firing_payload(item) for item in rows]}
