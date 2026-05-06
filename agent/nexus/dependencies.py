# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared dependencies and factories for FastAPI routers."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Optional

from fastapi import Depends, Request
from starlette.websockets import WebSocket

from nexus.config import settings
from nexus.history_repository import FirestoreHistoryRepository
from nexus.session import SessionManager
import redis

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int, name: str = "rate_limit") -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._redis: Optional[redis.Redis] = None
        if settings.redis_url:
            try:
                self._redis = redis.from_url(settings.redis_url)
            except Exception:
                logger.warning("Failed to connect to Redis for RateLimiter '%s'; falling back to in-memory.", name)
        
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        import time
        now = time.time()
        
        if self._redis:
            redis_key = f"rl:{self.name}:{key}"
            try:
                pipe = self._redis.pipeline()
                pipe.zremrangebyscore(redis_key, "-inf", now - self.window_seconds)
                pipe.zadd(redis_key, {str(now): now})
                pipe.zcard(redis_key)
                pipe.expire(redis_key, self.window_seconds)
                results = pipe.execute()
                count = results[2]
                return count <= self.max_requests
            except Exception as e:
                logger.warning("Redis rate limiter failed, falling back to memory: %s", e)

        with self._lock:
            timestamps = self._hits[key]
            timestamps = [t for t in timestamps if now - t <= self.window_seconds]
            if len(timestamps) >= self.max_requests:
                self._hits[key] = timestamps
                return False
            timestamps.append(now)
            self._hits[key] = timestamps
            return True


history_repository = FirestoreHistoryRepository()
session_manager = SessionManager(history_repository=history_repository)

session_create_limiter = RateLimiter(max_requests=5, window_seconds=60, name="session_create")
ticket_refresh_limiter = RateLimiter(max_requests=30, window_seconds=60, name="ticket_refresh")
ws_connect_limiter = RateLimiter(max_requests=30, window_seconds=60, name="ws_connect")

def get_history_repository() -> FirestoreHistoryRepository:
    return history_repository

def get_session_manager() -> SessionManager:
    return session_manager

def get_session_create_limiter() -> RateLimiter:
    return session_create_limiter

def get_ticket_refresh_limiter() -> RateLimiter:
    return ticket_refresh_limiter

def get_ws_connect_limiter() -> RateLimiter:
    return ws_connect_limiter

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
