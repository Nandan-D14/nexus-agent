"""Pydantic models for API request / response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Responses ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    active_sessions: int = 0


class SessionResponse(BaseModel):
    session_id: str
    stream_url: str
    ws_ticket: str
    status: str
    created_at: datetime


class SessionInfo(BaseModel):
    session_id: str
    status: str
    is_live: bool = True
    stream_url: Optional[str] = None
    created_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    message_count: int = 0


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""


class StatusMessage(BaseModel):
    status: str
