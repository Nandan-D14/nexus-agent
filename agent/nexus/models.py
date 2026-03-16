"""Pydantic models for API request / response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Responses ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    active_sessions: int = 0


class SessionResponse(BaseModel):
    session_id: str
    stream_url: Optional[str] = None
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


# ── User Settings ────────────────────────────────────────────────

class ByokResponse(BaseModel):
    e2bKeySet: bool = False
    geminiKeySet: bool = False
    geminiProvider: Literal["apiKey", "vertex"] = "apiKey"
    missing: list[str] = Field(default_factory=list)
    configured: bool = False
    vertexConfigured: bool = False
    sharedAccessEnabled: bool = False
    sharedAccessCodeConfigured: bool = False
    serverE2bConfigured: bool = False


class UserSettingsResponse(BaseModel):
    requireByok: bool = False
    googleDriveConnected: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    byok: ByokResponse = Field(default_factory=ByokResponse)


class ByokUpdateRequest(BaseModel):
    e2bApiKey: str | None = None
    geminiApiKey: str | None = None
    geminiProvider: Literal["apiKey", "vertex"] | None = None
    accessCode: str | None = None


class UserSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    byok: ByokUpdateRequest | None = None
