# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Cross-session Library listing for durable artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository
from nexus.library_artifacts import LIBRARY_CATEGORIES
from nexus.routers.files import _serialize_artifact

router = APIRouter()


def _parse_cursor(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="cursor must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_cursor(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/api/v1/library")
async def list_library_artifacts(
    limit: int = Query(100, ge=1, le=100),
    cursor: str | None = Query(None),
    q: str | None = Query(None),
    category: str | None = Query(None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    if category and category not in LIBRARY_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of: {', '.join(sorted(LIBRARY_CATEGORIES))}",
        )
    history_repository = get_history_repository()
    rows, next_cursor = await history_repository.list_owner_library_artifacts(
        user.uid,
        limit=limit,
        cursor=_parse_cursor(cursor),
        search=q,
        category=category,
    )
    return {
        "items": [
            {
                "artifact": _serialize_artifact(row.artifact).model_dump(mode="json"),
                "session_id": row.artifact.session_id,
                "session_title": row.session_title,
                "category": row.category,
            }
            for row in rows
        ],
        "next_cursor": _serialize_cursor(next_cursor),
    }
