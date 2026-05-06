# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""User data management endpoints."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, BackgroundTasks

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository
from nexus.storage import delete_user_artifacts_async
from nexus.models import StatusMessage

router = APIRouter()

@router.get("/api/v1/users/me/export")
async def export_my_data(user: AuthenticatedUser = Depends(require_current_user)):
    repo = get_history_repository()
    data = await repo.export_user_data(user.uid)
    return data

@router.delete("/api/v1/users/me", response_model=StatusMessage)
async def delete_my_data(
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_current_user)
):
    repo = get_history_repository()
    session_ids = await repo.delete_user_data(user.uid)
    background_tasks.add_task(delete_user_artifacts_async, user.uid, session_ids)
    return StatusMessage(status="deleted")
