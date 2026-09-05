# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Correlated, secret-safe runtime tracing primitives."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, replace
import hashlib
import re
import time
import uuid
from typing import Any
from urllib.parse import urlsplit


_SECRET_KEY_RE = re.compile(
    r"(authorization|cookie|credential|password|secret|token|api[_-]?key|private[_-]?key)",
    re.I,
)
_MAX_STRING = 2_000
_MAX_ITEMS = 30


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    run_id: str = ""
    step_id: str = ""
    parent_step_id: str = ""
    provider: str = ""
    model: str = ""


_current_trace: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "nexus_trace_context",
    default=None,
)


def new_trace_id(run_id: str = "") -> str:
    """Return a W3C-compatible 32-hex trace id.

    Durable run ids map deterministically so worker restarts retain correlation.
    Ephemeral turns get a random trace id.
    """

    if run_id:
        return hashlib.sha256(f"nexus:{run_id}".encode("utf-8")).hexdigest()[:32]
    return uuid.uuid4().hex


def new_step_id(prefix: str = "step") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def set_trace_context(context: TraceContext | None) -> contextvars.Token:
    return _current_trace.set(context)


def get_trace_context() -> TraceContext | None:
    return _current_trace.get()


def child_trace_context(
    *,
    step_id: str,
    provider: str | None = None,
    model: str | None = None,
) -> TraceContext:
    current = get_trace_context() or TraceContext(trace_id=new_trace_id())
    return replace(
        current,
        parent_step_id=current.step_id or current.parent_step_id,
        step_id=step_id,
        provider=provider if provider is not None else current.provider,
        model=model if model is not None else current.model,
    )


def trace_metadata(context: TraceContext | None = None) -> dict[str, str]:
    current = context or get_trace_context()
    if current is None:
        return {}
    result = {"trace_id": current.trace_id}
    if current.run_id:
        result["run_id"] = current.run_id
    if current.step_id:
        result["step_id"] = current.step_id
    if current.parent_step_id:
        result["parent_step_id"] = current.parent_step_id
    if current.provider:
        result["provider"] = current.provider
    if current.model:
        result["model"] = current.model
    return result


def trace_headers(context: TraceContext | None = None) -> dict[str, str]:
    current = context or get_trace_context()
    if current is None:
        return {}
    span_seed = current.step_id or uuid.uuid4().hex
    span_id = hashlib.sha256(span_seed.encode("utf-8")).hexdigest()[:16]
    headers = {
        "traceparent": f"00-{current.trace_id}-{span_id}-01",
        "X-Nexus-Trace-Id": current.trace_id,
    }
    if current.run_id:
        headers["X-Nexus-Run-Id"] = current.run_id
    if current.step_id:
        headers["X-Nexus-Step-Id"] = current.step_id
    return headers


def safe_trace_value(value: Any, *, depth: int = 0) -> Any:
    """Redact secrets and bound arbitrary values before persistence or UI."""

    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, raw in list(value.items())[:_MAX_ITEMS]:
            key_text = str(key)
            result[key_text] = (
                "[redacted]"
                if _SECRET_KEY_RE.search(key_text)
                else safe_trace_value(raw, depth=depth + 1)
            )
        return result
    if isinstance(value, (list, tuple, set)):
        return [
            safe_trace_value(item, depth=depth + 1)
            for item in list(value)[:_MAX_ITEMS]
        ]
    if isinstance(value, bytes):
        return f"[bytes:{len(value)}]"
    if isinstance(value, str):
        return value[:_MAX_STRING]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_STRING]


def safe_origin(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.hostname:
            return "[invalid-url]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"
    except Exception:
        return "[invalid-url]"


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def result_status(result: dict[str, Any]) -> tuple[str, str, str]:
    status = str(result.get("status") or "").strip().lower()
    error_code = str(result.get("error_code") or result.get("code") or "")
    retry_reason = str(
        result.get("retry_reason")
        or result.get("fallback_reason")
        or result.get("error")
        or ""
    )[:500]
    if status in {"error", "failed", "cancelled", "denied"} or error_code:
        return (status or "error", error_code, retry_reason)
    return (status or "success", error_code, retry_reason)


__all__ = [
    "TraceContext",
    "child_trace_context",
    "get_trace_context",
    "monotonic_ms",
    "new_step_id",
    "new_trace_id",
    "result_status",
    "safe_origin",
    "safe_trace_value",
    "set_trace_context",
    "trace_headers",
    "trace_metadata",
]
