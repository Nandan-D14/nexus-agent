# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared helpers that keep Firestore writes resilient to contention.

Two complementary mechanisms:

* ``guarded_write`` serializes writes that share a hot document (keyed by
  session id or task id) so a single session fanning out parallel tool
  results does not self-contend inside Firestore transactions. Writes for
  different keys stay fully concurrent.
* ``run_with_write_retry`` adds a bounded jittered-backoff retry on top of
  Firestore's own transaction retry, so residual cross-instance contention
  (``Aborted``) is smoothed out instead of surfacing as a hard failure.

Both are guarded by config flags and default to preserving existing behavior.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from typing import Callable, TypeVar

from google.api_core.exceptions import Aborted, ServiceUnavailable

from nexus.config import settings

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Transient Firestore errors worth retrying. Aborted is raised on
# cross-transaction contention; ServiceUnavailable on transient RPC issues.
_RETRYABLE_ERRORS = (Aborted, ServiceUnavailable)

# Per-key asyncio locks. Accessed only from the event-loop thread, so plain
# dict access is safe (no cross-thread mutation).
_write_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    lock = _write_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _write_locks[key] = lock
    return lock


@contextlib.asynccontextmanager
async def guarded_write(key: str | None):
    """Serialize writes sharing a hot document, keyed by session/task id.

    No-op when ``serialize_session_writes`` is disabled or ``key`` is falsy,
    so call sites can wrap unconditionally.
    """
    if not settings.serialize_session_writes or not key:
        yield
        return
    async with _lock_for(key):
        yield


def run_with_write_retry(
    fn: Callable[[], _T],
    *,
    description: str = "firestore_write",
) -> _T:
    """Run a sync Firestore write, retrying transient contention with backoff.

    Retries only on ``Aborted`` / ``ServiceUnavailable``. Meant to run inside a
    worker thread (uses ``time.sleep``), layered on Firestore's own retry.
    """
    attempts = max(1, settings.firestore_write_max_retries)
    base_ms = max(1, settings.firestore_write_backoff_base_ms)
    max_ms = max(base_ms, settings.firestore_write_backoff_max_ms)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except _RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            ceiling_ms = min(max_ms, base_ms * (2 ** (attempt - 1)))
            sleep_s = random.uniform(0.0, ceiling_ms) / 1000.0
            logger.warning(
                "Firestore write '%s' contended (attempt %d/%d); retrying in %.3fs",
                description,
                attempt,
                attempts,
                sleep_s,
            )
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc
