# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared dependencies and factories for FastAPI routers."""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.websockets import WebSocket

from nexus.history_repository import FirestoreHistoryRepository
from nexus.production_tasks import ProductionTaskRepository
from nexus.rate_limit import RateLimiter
from nexus.repositories.schedule_store import ScheduleStore
from nexus.sandbox import SandboxLifecycleController
from nexus.session import SessionManager
from nexus.task_queue import task_queue, TaskQueue

logger = logging.getLogger(__name__)

__all__ = ["RateLimiter"]


history_repository = FirestoreHistoryRepository()
production_task_repository = ProductionTaskRepository()
schedule_store = ScheduleStore()
session_manager = SessionManager(history_repository=history_repository)
sandbox_lifecycle_controller = SandboxLifecycleController(history_repository)

session_create_limiter = RateLimiter(max_requests=5, window_seconds=60, name="session_create")
ticket_refresh_limiter = RateLimiter(max_requests=30, window_seconds=60, name="ticket_refresh")
ws_connect_limiter = RateLimiter(max_requests=30, window_seconds=60, name="ws_connect")
task_create_limiter = RateLimiter(max_requests=20, window_seconds=60, name="task_create")
schedule_create_limiter = RateLimiter(max_requests=10, window_seconds=60, name="schedule_create")
oauth_url_limiter = RateLimiter(max_requests=30, window_seconds=60, name="oauth_url")
llm_probe_limiter = RateLimiter(max_requests=10, window_seconds=60, name="llm_probe")
settings_update_limiter = RateLimiter(max_requests=20, window_seconds=60, name="settings_update")
integration_test_limiter = RateLimiter(max_requests=10, window_seconds=60, name="integration_test")

def get_history_repository() -> FirestoreHistoryRepository:
    return history_repository

def get_session_manager() -> SessionManager:
    return session_manager

def get_production_task_repository() -> ProductionTaskRepository:
    return production_task_repository

def get_schedule_store() -> ScheduleStore:
    return schedule_store

def get_task_queue() -> TaskQueue:
    return task_queue

def get_sandbox_lifecycle_controller() -> SandboxLifecycleController:
    return sandbox_lifecycle_controller

def get_session_create_limiter() -> RateLimiter:
    return session_create_limiter

def get_ticket_refresh_limiter() -> RateLimiter:
    return ticket_refresh_limiter

def get_ws_connect_limiter() -> RateLimiter:
    return ws_connect_limiter

def get_task_create_limiter() -> RateLimiter:
    return task_create_limiter

def get_schedule_create_limiter() -> RateLimiter:
    return schedule_create_limiter

def get_oauth_url_limiter() -> RateLimiter:
    return oauth_url_limiter

def get_llm_probe_limiter() -> RateLimiter:
    return llm_probe_limiter

def get_settings_update_limiter() -> RateLimiter:
    return settings_update_limiter

def get_integration_test_limiter() -> RateLimiter:
    return integration_test_limiter

def get_client_ip(request: Request) -> str:
    """Helper to extract IP from Request for rate limiting."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"

def get_ws_client_ip(ws: WebSocket) -> str:
    """Helper to extract IP from WebSocket for rate limiting."""
    forwarded = ws.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if ws.client:
        return ws.client.host
    return "127.0.0.1"
