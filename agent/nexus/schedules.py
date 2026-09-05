# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Schedule definitions, next-run math, and unattended-tool allowlists."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ScheduleFreq = Literal["once", "daily", "weekdays", "weekly", "monthly", "custom"]
ScheduleStatus = Literal["active", "paused", "completed"]
RunMode = Literal["new_task", "continue_task"]

SCHEDULE_FREQS: frozenset[str] = frozenset(
    {"once", "daily", "weekdays", "weekly", "monthly", "custom"}
)
SCHEDULE_STATUSES: frozenset[str] = frozenset({"active", "paused", "completed"})
RUN_MODES: frozenset[str] = frozenset({"new_task", "continue_task"})
IN_FLIGHT_RUN_STATUSES: frozenset[str] = frozenset(
    {"queued", "running", "waiting_approval", "cancelling"}
)

ALLOWED_UNATTENDED_TOOLS: frozenset[str] = frozenset(
    {
        "gmail_send",
        "create_drive_doc",
        "create_drive_sheet",
        "upload_drive_file",
        "tasks_create",
        "slack_post",
    }
)
NEVER_UNATTENDED_TOOLS: frozenset[str] = frozenset(
    {
        "github_push",
        "github_create_repo",
        "vyora_start_call",
        "run_command",
    }
)

MAX_ACTIVE_SCHEDULES = 20
_SLACK_MCP_REMOTE_RE = ("post", "send", "chat")


def sanitize_unattended_tools(values: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        name = str(item).strip()
        if name not in ALLOWED_UNATTENDED_TOOLS or name in NEVER_UNATTENDED_TOOLS:
            continue
        if name in seen:
            continue
        seen.add(name)
        cleaned.append(name)
    return cleaned


def parse_time_of_day(value: str) -> time:
    raw = (value or "09:00").strip()
    parts = raw.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid time of day: {value}")
    return time(hour=hour, minute=minute)


def resolve_zone(timezone_name: str) -> ZoneInfo:
    name = (timezone_name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def next_run_at(
    *,
    freq: str,
    timezone_name: str = "UTC",
    time_of_day: str = "09:00",
    days_of_week: list[int] | None = None,
    once_at: datetime | None = None,
    after: datetime | None = None,
    day_of_month: int = 1,
) -> datetime | None:
    """Return the next UTC instant after ``after`` for this cadence."""
    freq_norm = str(freq or "").strip().lower()
    if freq_norm not in SCHEDULE_FREQS:
        raise ValueError(f"Unsupported schedule frequency: {freq}")
    tz = resolve_zone(timezone_name)
    after_utc = _as_utc(after or datetime.now(timezone.utc))
    after_local = after_utc.astimezone(tz)

    if freq_norm == "once":
        if once_at is None:
            return None
        instant = once_at
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=tz)
        instant_utc = _as_utc(instant)
        if instant_utc <= after_utc:
            return None
        return instant_utc

    tod = parse_time_of_day(time_of_day)
    wanted_days = {int(day) for day in (days_of_week or []) if 0 <= int(day) <= 6}
    month_day = min(max(int(day_of_month or 1), 1), 31)
    start_date = after_local.date()
    for offset in range(0, 400):
        day = start_date + timedelta(days=offset)
        candidate_local = datetime.combine(day, tod, tzinfo=tz)
        if candidate_local <= after_local:
            continue
        weekday = day.weekday()
        if freq_norm == "daily":
            return _as_utc(candidate_local)
        if freq_norm == "weekdays" and weekday < 5:
            return _as_utc(candidate_local)
        if freq_norm in {"weekly", "custom"}:
            if not wanted_days or weekday in wanted_days:
                return _as_utc(candidate_local)
            continue
        if freq_norm == "monthly":
            last_day = calendar.monthrange(day.year, day.month)[1]
            if day.day == min(month_day, last_day):
                return _as_utc(candidate_local)
    return None


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _as_utc(parsed)


def compute_next_run(schedule: Schedule, *, after: datetime | None = None) -> datetime | None:
    days = [int(day) for day in schedule.days_of_week if 0 <= int(day) <= 6]
    if schedule.freq in {"weekly", "custom"} and not days:
        tz = resolve_zone(schedule.timezone)
        local = _as_utc(after or datetime.now(timezone.utc)).astimezone(tz)
        days = [local.weekday()]
    return next_run_at(
        freq=schedule.freq,
        timezone_name=schedule.timezone,
        time_of_day=schedule.time_of_day,
        days_of_week=days,
        once_at=schedule.once_at,
        after=after,
        day_of_month=schedule.day_of_month,
    )


def schedule_payload(schedule: Schedule) -> dict[str, Any]:
    return {
        "schedule_id": schedule.schedule_id,
        "owner_id": schedule.owner_id,
        "title": schedule.title,
        "prompt": schedule.prompt,
        "timezone": schedule.timezone,
        "freq": schedule.freq,
        "time_of_day": schedule.time_of_day,
        "days_of_week": list(schedule.days_of_week),
        "once_at": isoformat_utc(schedule.once_at),
        "day_of_month": schedule.day_of_month,
        "next_run_at": isoformat_utc(schedule.next_run_at),
        "last_run_at": isoformat_utc(schedule.last_run_at),
        "status": schedule.status,
        "run_mode": schedule.run_mode,
        "continue_task_id": schedule.continue_task_id,
        "connector_ids": list(schedule.connector_ids),
        "tool_ids": list(schedule.tool_ids),
        "autonomy_mode": schedule.autonomy_mode,
        "skip_confirmations": schedule.skip_confirmations,
        "allowed_unattended_tools": list(schedule.allowed_unattended_tools),
        "current_run_id": schedule.current_run_id,
        "last_task_id": schedule.last_task_id,
        "last_session_id": schedule.last_session_id,
        "created_at": isoformat_utc(schedule.created_at),
        "updated_at": isoformat_utc(schedule.updated_at),
        "metadata": dict(schedule.metadata or {}),
    }


def firing_payload(firing: ScheduleFiring) -> dict[str, Any]:
    return {
        "firing_id": firing.firing_id,
        "schedule_id": firing.schedule_id,
        "owner_id": firing.owner_id,
        "scheduled_for": isoformat_utc(firing.scheduled_for),
        "task_id": firing.task_id,
        "run_id": firing.run_id,
        "session_id": firing.session_id,
        "status": firing.status,
        "error": firing.error,
        "created_at": isoformat_utc(firing.created_at),
    }


def slack_mcp_unattended_allowed(tool_name: str, allowed: set[str]) -> bool:
    if "slack_post" not in allowed:
        return False
    if not str(tool_name).startswith("mcp__"):
        return False
    remote = str(tool_name).rsplit("__", 1)[-1].lower()
    return any(token in remote for token in _SLACK_MCP_REMOTE_RE)


@dataclass
class Schedule:
    schedule_id: str
    owner_id: str
    title: str
    prompt: str
    timezone: str = "UTC"
    freq: str = "daily"
    time_of_day: str = "09:00"
    days_of_week: list[int] = field(default_factory=list)
    once_at: datetime | None = None
    day_of_month: int = 1
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    status: str = "active"
    run_mode: str = "new_task"
    continue_task_id: str | None = None
    connector_ids: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    autonomy_mode: str = "manual"
    skip_confirmations: bool = False
    allowed_unattended_tools: list[str] = field(default_factory=list)
    current_run_id: str | None = None
    last_task_id: str | None = None
    last_session_id: str | None = None
    dispatch_lock_until: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduleFiring:
    firing_id: str
    schedule_id: str
    owner_id: str
    scheduled_for: datetime | None = None
    task_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    status: str = "queued"
    error: str | None = None
    created_at: datetime | None = None
