# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""FastAPI application — REST + WebSocket endpoints for CoComputer."""

from __future__ import annotations

import logging
import uuid
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted
from pythonjsonlogger import jsonlogger

from nexus.config import settings, apply_runtime_env_overrides, validate_startup_settings
from nexus.dependencies import (
    get_history_repository,
    get_production_task_repository,
    get_session_manager,
    get_task_queue,
)
from nexus.sandbox import SandboxSweeper
from nexus.task_recovery import StaleRunSweeper

# authlib 1.x still imports authlib.jose internally (via _joserfc_helpers) even
# though it recommends joserfc. We already depend on joserfc; silence the
# transitional deprecation until authlib 2.0 drops the shim.
warnings.filterwarnings(
    "ignore",
    message=r".*authlib\.jose module is deprecated.*",
    category=DeprecationWarning,
)

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
    if settings.qwen_capability_probe_on_startup:
        should_probe = settings.is_production or settings.strict_config_validation
        if should_probe:
            from nexus.vision_provider import probe_qwen_capabilities

            report = await probe_qwen_capabilities()
            module_logger.info(
                "Qwen capability probe passed text_model=%s vision_model=%s",
                report.text_model,
                report.vision_model,
            )
        elif settings.qwen_api_key.strip():
            module_logger.info(
                "Qwen capability probe deferred (non-production); "
                "set STRICT_CONFIG_VALIDATION=true to force at startup"
            )
        else:
            module_logger.warning(
                "Qwen capability probe skipped: QWEN_API_KEY is not configured"
            )
    
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    
    session_manager.start_cleanup()

    # Start the sandbox sweeper
    sweeper = SandboxSweeper(history_repository)
    await sweeper.start(interval_seconds=3600)  # Sweep every hour
    stale_run_sweeper = StaleRunSweeper(
        get_production_task_repository(),
        get_task_queue(),
    )
    await stale_run_sweeper.start()

    yield

    # Stop the sandbox sweeper
    await stale_run_sweeper.stop()
    await sweeper.stop()

    module_logger.info("CoComputer agent service shutting down...")
    session_manager.stop_cleanup()
    await session_manager.destroy_all()


app = FastAPI(
    title="CoComputer Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(GoogleAPICallError)
async def google_api_unavailable_handler(request: Request, exc: GoogleAPICallError):
    """Return a retryable response instead of leaking a Google API traceback."""
    request_id = getattr(request.state, "request_id", "unknown")
    error_name = type(exc).__name__
    error_message = str(exc).strip() or error_name

    if isinstance(exc, ResourceExhausted):
        module_logger.warning(
            "Google API quota exceeded (request_id=%s, path=%s, error=%s, message=%s)",
            request_id,
            request.url.path,
            error_name,
            error_message,
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": {
                    "code": "GOOGLE_QUOTA_EXCEEDED",
                    "detail": (
                        "Firestore quota exceeded. Check GCP quotas/billing for this "
                        "project, then retry."
                    ),
                }
            },
            headers={"Retry-After": "60"},
        )

    module_logger.warning(
        "Google API temporarily unavailable (request_id=%s, path=%s, error=%s, message=%s)",
        request_id,
        request.url.path,
        error_name,
        error_message,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "GOOGLE_SERVICE_UNAVAILABLE",
                "detail": "Google-backed storage is temporarily unavailable. Please retry shortly.",
            }
        },
        headers={"Retry-After": "5"},
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
    ws_router,
    auth_router,
    skills_router,
    integrations_router,
    files_router,
    templates_router,
    sessions_router,
    library_router,
    users_router,
    tasks_router,
    worker_router,
)

app.include_router(health_router)
app.include_router(ws_router)
app.include_router(auth_router)
app.include_router(skills_router)
app.include_router(integrations_router)
app.include_router(files_router)
app.include_router(templates_router)
app.include_router(sessions_router)
app.include_router(library_router)
app.include_router(users_router)
app.include_router(tasks_router)
app.include_router(worker_router)
