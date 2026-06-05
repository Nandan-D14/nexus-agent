# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Base utilities for tools — normalization decorator and error helpers.

Every tool in CoComputer should use ``@normalized_tool`` so the LLM always
receives a predictable ``NormalizedToolResult`` shape regardless of which
tool was called.
"""

from __future__ import annotations

import asyncio
from functools import wraps
import logging
from typing import Any, Callable, TypedDict

logger = logging.getLogger(__name__)

_NORMALIZED_KEYS = frozenset({
    "status", "summary", "detail", "metadata",
    "error_code", "suggested_alternatives", "retry_after",
})


class NormalizedToolResult(TypedDict, total=False):
    """Standard return shape for every tool in CoComputer.

    Fields
    ------
    status : ``"success"`` or ``"error"``
    summary : One-line human-readable description of what happened.
    detail : Full result payload (dict, list, or string).
    metadata : Extra context (timestamps, counts, paths, etc.).
    error_code : Machine-readable error category for LLM routing decisions.
        Common values: ``"RATE_LIMIT"``, ``"PERMISSION_DENIED"``,
        ``"NOT_FOUND"``, ``"TIMEOUT"``, ``"INVALID_INPUT"``, ``"AUTH_REQUIRED"``.
    suggested_alternatives : Other tool names the LLM could try instead.
    retry_after : Seconds to wait before retrying (for rate-limit errors).
    """

    status: str
    summary: str
    detail: Any
    metadata: dict[str, Any]
    error_code: str
    suggested_alternatives: list[str]
    retry_after: int


def tool_error(
    message: str,
    *,
    error_code: str = "",
    suggested_alternatives: list[str] | None = None,
    retry_after: int | None = None,
    **metadata: Any,
) -> NormalizedToolResult:
    """Build a consistent error result for any tool.

    Usage::

        return tool_error("Drive not connected", error_code="AUTH_REQUIRED",
                          suggested_alternatives=["web_search"])
    """
    result: NormalizedToolResult = {
        "status": "error",
        "summary": message,
        "detail": message,
        "metadata": metadata,
        "error_code": error_code,
        "suggested_alternatives": suggested_alternatives or [],
    }
    if retry_after is not None:
        result["retry_after"] = retry_after
    return result


def tool_success(
    summary: str,
    *,
    detail: Any = None,
    **metadata: Any,
) -> NormalizedToolResult:
    """Build a consistent success result for any tool."""
    return {
        "status": "success",
        "summary": summary,
        "detail": detail if detail is not None else summary,
        "metadata": metadata,
        "error_code": "",
        "suggested_alternatives": [],
    }


def normalized_tool(func: Callable) -> Callable:
    """Decorator that normalizes tool outputs into ``NormalizedToolResult``.

    Works with both sync and async tool functions. Catches all exceptions
    and converts them into structured error results so the LLM always
    receives a valid response.
    """

    @wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> NormalizedToolResult:
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return _normalize(func.__name__, result)
        except Exception as e:
            logger.exception("Tool %s failed", func.__name__)
            return tool_error(
                f"Tool {func.__name__} failed: {e}",
                error_code="TOOL_EXCEPTION",
                tool_name=func.__name__,
            )

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> NormalizedToolResult:
        try:
            result = func(*args, **kwargs)
            return _normalize(func.__name__, result)
        except Exception as e:
            logger.exception("Tool %s failed", func.__name__)
            return tool_error(
                f"Tool {func.__name__} failed: {e}",
                error_code="TOOL_EXCEPTION",
                tool_name=func.__name__,
            )

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


def _normalize(func_name: str, result: Any) -> NormalizedToolResult:
    """Convert any tool return value into a ``NormalizedToolResult``."""
    if isinstance(result, dict):
        # Already a NormalizedToolResult — fill in missing keys
        if "status" in result and "summary" in result:
            return {
                "status": result.get("status", "success"),
                "summary": result.get("summary", ""),
                "detail": result.get("detail", result),
                "metadata": result.get("metadata", {}),
                "error_code": result.get("error_code", ""),
                "suggested_alternatives": result.get("suggested_alternatives", []),
                **({"retry_after": result["retry_after"]} if "retry_after" in result else {}),
            }

        # Legacy dict with "error" key
        if "error" in result:
            meta = {k: v for k, v in result.items() if k not in _NORMALIZED_KEYS and k != "error"}
            return {
                "status": "error",
                "summary": result["error"],
                "detail": result,
                "metadata": meta,
                "error_code": result.get("error_code", ""),
                "suggested_alternatives": result.get("suggested_alternatives", []),
            }

        # Legacy dict with "status" key (e.g. {"status": "success", "message": "..."})
        if "status" in result:
            summary = (
                result.get("summary")
                or result.get("message")
                or result.get("description")
                or f"Executed {func_name}"
            )
            meta = {k: v for k, v in result.items() if k not in _NORMALIZED_KEYS and k not in ("message", "description")}
            return {
                "status": result.get("status", "success"),
                "summary": summary,
                "detail": result,
                "metadata": meta,
                "error_code": result.get("error_code", ""),
                "suggested_alternatives": result.get("suggested_alternatives", []),
            }

        # Plain data dict — treat as success
        return {
            "status": "success",
            "summary": result.get("summary") or result.get("description") or f"Executed {func_name}",
            "detail": result,
            "metadata": {k: v for k, v in result.items() if k not in _NORMALIZED_KEYS},
            "error_code": "",
            "suggested_alternatives": [],
        }

    # Non-dict result (string, list, etc.)
    return {
        "status": "success",
        "summary": str(result)[:200] if result else f"Executed {func_name}",
        "detail": result,
        "metadata": {},
        "error_code": "",
        "suggested_alternatives": [],
    }
