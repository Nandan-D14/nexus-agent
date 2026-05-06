# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""FastAPI application — REST + WebSocket endpoints for CoComputer."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger import jsonlogger

from nexus.config import settings, apply_runtime_env_overrides, validate_startup_settings
from nexus.dependencies import get_session_manager, get_history_repository
from nexus.sandbox import SandboxSweeper

# Set up structured JSON logging
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# Suppress noisy loggers
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

module_logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    apply_runtime_env_overrides()
    validate_startup_settings()
    module_logger.info("CoComputer agent service starting...")
    
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    
    session_manager.start_cleanup()

    # Start the sandbox sweeper
    sweeper = SandboxSweeper(history_repository)
    await sweeper.start(interval_seconds=3600)  # Sweep every hour

    yield

    # Stop the sandbox sweeper
    await sweeper.stop()

    module_logger.info("CoComputer agent service shutting down...")
    session_manager.stop_cleanup()
    await session_manager.destroy_all()


app = FastAPI(
    title="CoComputer Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — conditionally allow localhost
origins = [settings.frontend_url]
if not settings.is_production:
    origins.extend(["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Include Routers ──────────────────────────────────────────────

from nexus.routers import (
    health_router,
    beta_router,
    ws_router,
    auth_router,
    skills_router,
    integrations_router,
    files_router,
    templates_router,
    sessions_router,
    users_router,
)

app.include_router(health_router)
app.include_router(beta_router)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(skills_router)
app.include_router(integrations_router)
app.include_router(files_router)
app.include_router(templates_router)
app.include_router(sessions_router)
app.include_router(users_router)
