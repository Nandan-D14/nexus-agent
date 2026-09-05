# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Liveness beacon for agent runs.

The durable worker renews its Firestore lease on a fixed timer, and every
recovery path in the system treats a live lease as proof that a worker is
genuinely making progress: ``_abandoned_run_reason`` refuses to settle a leased
run, and the stale-run sweeper only queries runs whose lease has *expired*.

That makes a blind heartbeat dangerous. A worker wedged inside a hung model
stream keeps renewing, so its run stays non-terminal, and every later prompt on
that session is refused as ``run_busy`` until the process dies. A lease has to
mean "work is happening", not "the process is alive".

Progress is recorded from two places: the orchestrator's ADK event callback,
and the tool gateway. The tool gateway also tracks *in-flight* calls, because a
single tool can legitimately run for minutes (sandbox provisioning, playwright
installs) without producing an agent event. Only silence with no tool running
counts as a stall, which lets the stall threshold stay tight enough to be useful
against a hung model stream.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# run_id -> monotonic timestamp of the last observed agent activity.
_last_progress: dict[str, float] = {}
# run_id -> number of tool calls currently executing.
_tools_in_flight: dict[str, int] = {}


def start_tracking(run_id: str | None) -> None:
    """Begin tracking a run, seeding it with the current time."""
    if not run_id:
        return
    _last_progress[run_id] = time.monotonic()


def mark_progress(run_id: str | None) -> None:
    """Record that the run just did something observable."""
    if not run_id:
        return
    # Only refresh runs that are actively tracked. A stray mark from a
    # background task must not resurrect a run the worker already gave up on.
    if run_id in _last_progress:
        _last_progress[run_id] = time.monotonic()


def stop_tracking(run_id: str | None) -> None:
    """Forget a run once it is settled."""
    if not run_id:
        return
    _last_progress.pop(run_id, None)
    _tools_in_flight.pop(run_id, None)


def tool_started(run_id: str | None) -> None:
    """Note that a tool call began, suspending the stall check."""
    if not run_id:
        return
    _tools_in_flight[run_id] = _tools_in_flight.get(run_id, 0) + 1
    mark_progress(run_id)


def tool_finished(run_id: str | None) -> None:
    """Note that a tool call ended, resuming the stall check."""
    if not run_id:
        return
    remaining = _tools_in_flight.get(run_id, 0) - 1
    if remaining > 0:
        _tools_in_flight[run_id] = remaining
    else:
        _tools_in_flight.pop(run_id, None)
    mark_progress(run_id)


def seconds_since_progress(run_id: str | None) -> float | None:
    """Seconds since the run last showed activity, or None if untracked."""
    if not run_id:
        return None
    last = _last_progress.get(run_id)
    if last is None:
        return None
    return max(0.0, time.monotonic() - last)


def is_stalled(run_id: str | None, timeout: float) -> bool:
    """Whether the run has produced nothing for longer than ``timeout``.

    A run with a tool in flight is never stalled: tools carry their own
    deadlines, and a long install would otherwise look identical to a hang.
    """
    if timeout <= 0 or not run_id:
        return False
    if _tools_in_flight.get(run_id):
        return False
    idle = seconds_since_progress(run_id)
    return idle is not None and idle > timeout
