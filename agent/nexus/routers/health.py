# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Health check endpoints."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel

from nexus.config import settings

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    environment: str

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check returning environment info."""
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
    )

@router.get("/healthz")
async def liveness_probe() -> dict[str, Any]:
    """Kubernetes liveness probe."""
    return {"status": "ok"}
