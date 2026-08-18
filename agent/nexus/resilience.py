# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Bounded retry + deadline helpers shared by tools and providers.

Every remote call the agent depends on (vision, screen capture, search,
model routing) must fail in bounded time so the turn can continue with a
degraded-but-honest result instead of hanging. The helpers here give a
single place to express "try N times with backoff, then give up".
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import logging
import random
import time
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Threads for abandoned blocking calls. A wedged SDK call cannot be killed,
# so the worker thread is left to finish on its own while the caller moves
# on; the pool is unbounded-by-name but bounded by how often deadlines fire.
_deadline_pool = ThreadPoolExecutor(thread_name_prefix="nexus-deadline")


class DeadlineExceeded(TimeoutError):
    """Raised when a blocking call outlives its deadline."""


def _sleep_for(attempt: int, base_delay: float, max_delay: float, jitter: bool) -> float:
    """Exponential backoff with optional full jitter."""
    delay = min(base_delay * (2 ** max(0, attempt - 1)), max_delay)
    if jitter and delay > 0:
        delay = random.uniform(delay / 2, delay)
    return max(0.0, delay)


def retry_sync(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: bool = True,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    give_up_on: tuple[type[BaseException], ...] = (),
    label: str = "operation",
    timeout: float | None = None,
) -> T:
    """Call ``operation`` up to ``attempts`` times, then re-raise the last error.

    ``timeout`` applies a per-attempt deadline for blocking calls that have no
    timeout of their own. Exceptions in ``give_up_on`` abort immediately —
    use it for errors that retrying cannot fix (bad credentials, bad input).
    """
    total = max(1, int(attempts))
    last_error: BaseException | None = None

    for attempt in range(1, total + 1):
        try:
            if timeout is not None:
                return call_with_deadline(operation, timeout=timeout, label=label)
            return operation()
        except give_up_on:
            raise
        except retry_on as exc:
            last_error = exc
            if attempt >= total:
                break
            delay = _sleep_for(attempt, base_delay, max_delay, jitter)
            logger.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.2fs",
                label,
                attempt,
                total,
                f"{type(exc).__name__}: {str(exc)[:200]}",
                delay,
            )
            if delay:
                time.sleep(delay)

    assert last_error is not None
    logger.error("%s failed after %d attempt(s)", label, total)
    raise last_error


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: bool = True,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    give_up_on: tuple[type[BaseException], ...] = (),
    label: str = "operation",
    timeout: float | None = None,
) -> T:
    """Async counterpart of :func:`retry_sync`.

    ``timeout`` is a per-attempt wall clock applied with ``asyncio.wait_for``,
    so a stalled awaitable cannot hold the turn open indefinitely.
    """
    total = max(1, int(attempts))
    last_error: BaseException | None = None

    for attempt in range(1, total + 1):
        try:
            if timeout is not None:
                return await asyncio.wait_for(operation(), timeout=timeout)
            return await operation()
        except asyncio.CancelledError:
            raise
        except give_up_on:
            raise
        except retry_on as exc:
            last_error = exc
            if attempt >= total:
                break
            delay = _sleep_for(attempt, base_delay, max_delay, jitter)
            logger.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.2fs",
                label,
                attempt,
                total,
                f"{type(exc).__name__}: {str(exc)[:200]}",
                delay,
            )
            if delay:
                await asyncio.sleep(delay)

    assert last_error is not None
    logger.error("%s failed after %d attempt(s)", label, total)
    raise last_error


def call_with_deadline(
    operation: Callable[[], T],
    *,
    timeout: float,
    label: str = "operation",
) -> T:
    """Run a blocking callable, raising :class:`DeadlineExceeded` past ``timeout``.

    The underlying thread is abandoned rather than killed — Python cannot
    interrupt a blocked C call — so this bounds the *caller's* wait, not the
    thread's lifetime.
    """
    future = _deadline_pool.submit(operation)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        future.cancel()
        raise DeadlineExceeded(
            f"{label} exceeded its {timeout:.1f}s deadline"
        ) from exc


def is_remote_deadline_error(exc: BaseException | str) -> bool:
    """True for gRPC/Firestore/GCS deadline failures that look like HTTP 504s."""
    text = str(exc).lower()
    return (
        "deadline exceeded" in text
        or "stream removed" in text
        or "504 stream" in text
    )


__all__ = [
    "DeadlineExceeded",
    "call_with_deadline",
    "is_remote_deadline_error",
    "retry_async",
    "retry_sync",
]
