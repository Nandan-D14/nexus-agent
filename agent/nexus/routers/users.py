# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""User data management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import RateLimiter, get_history_repository
from nexus.storage import delete_user_artifacts_async
from nexus.models import StatusMessage

router = APIRouter()

# Both endpoints read or delete a user's entire history; keep them rare.
_account_data_limiter = RateLimiter(max_requests=3, window_seconds=3600, name="account_data")


def _check_rate(uid: str) -> None:
    if not _account_data_limiter.check(uid):
        raise HTTPException(status_code=429, detail="Too many export/delete requests; try again later.")


@router.get("/api/v1/users/me/export")
async def export_my_data(user: AuthenticatedUser = Depends(require_current_user)):
    _check_rate(user.uid)
    repo = get_history_repository()
    data = await repo.export_user_data(user.uid)
    return data

@router.delete("/api/v1/users/me", response_model=StatusMessage)
async def delete_my_data(
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_current_user)
):
    _check_rate(user.uid)
    repo = get_history_repository()
    session_ids = await repo.delete_user_data(user.uid)
    background_tasks.add_task(delete_user_artifacts_async, user.uid, session_ids)
    return StatusMessage(status="deleted")
