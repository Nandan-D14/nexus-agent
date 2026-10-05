# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Sliding-window rate limiter shared by HTTP routes and the WebSocket handler.

Redis (when configured) makes limits global across Cloud Run instances. The
in-memory fallback is per process and bounded so idle keys cannot grow forever.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

import redis

from nexus.config import settings

logger = logging.getLogger(__name__)

# Upper bound on distinct keys tracked by the in-memory fallback.
_MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int, name: str = "rate_limit") -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._redis: Optional[redis.Redis] = None
        if settings.redis_url:
            try:
                self._redis = redis.from_url(
                    settings.redis_url,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
            except Exception:
                logger.warning("Failed to connect to Redis for RateLimiter '%s'; falling back to in-memory.", name)

        self._hits: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.time()

        if self._redis:
            redis_key = f"rl:{self.name}:{key}"
            try:
                # Sorted-set sliding window: unlike INCR+EXPIRE, steady traffic
                # cannot keep the counter alive forever.
                pipe = self._redis.pipeline()
                pipe.zremrangebyscore(redis_key, "-inf", now - self.window_seconds)
                pipe.zadd(redis_key, {f"{now}:{time.monotonic_ns()}": now})
                pipe.zcard(redis_key)
                pipe.expire(redis_key, self.window_seconds)
                results = pipe.execute()
                return results[2] <= self.max_requests
            except Exception as e:
                logger.warning("Redis rate limiter failed, falling back to memory: %s", e)

        with self._lock:
            timestamps = [t for t in self._hits.pop(key, []) if now - t <= self.window_seconds]
            allowed = len(timestamps) < self.max_requests
            if allowed:
                timestamps.append(now)
            if timestamps:
                self._hits[key] = timestamps  # re-insert as most recently used
            while len(self._hits) > _MAX_TRACKED_KEYS:
                self._hits.popitem(last=False)
            return allowed

    # WebSocket handler call-site name.
    is_allowed = check
