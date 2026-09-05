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
    "error_code", "suggested_alternatives", "retry_after", "retryable",
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
    retryable : Whether the caller should retry (sandbox reconnect, transient faults).
    """

    status: str
    summary: str
    detail: Any
    metadata: dict[str, Any]
    error_code: str
    suggested_alternatives: list[str]
    retry_after: int
    retryable: bool


def reraise_if_sandbox_dead(exc: BaseException) -> None:
    """Let a dead-sandbox fault escape a tool body.

    Tool bodies that catch bare ``Exception`` swallow ``SandboxDeadError``,
    which silently disables the reconnect-and-retry-once path in
    ``normalized_tool``. Call this first in such handlers so the decorator can
    rebuild the sandbox instead of handing the model a generic tool error for
    a machine that no longer exists.
    """
    from nexus.sandbox import SandboxDeadError

    if isinstance(exc, SandboxDeadError):
        raise exc


def tool_error(
    message: str,
    *,
    error_code: str = "",
    suggested_alternatives: list[str] | None = None,
    retry_after: int | None = None,
    retryable: bool | None = None,
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
    if retryable is not None:
        result["retryable"] = retryable
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


def normalized_tool(func: Callable = None, *, needs_sandbox: bool = False) -> Callable:
    """Decorator that normalizes tool outputs into ``NormalizedToolResult``.

    Works with both sync and async tool functions. Catches all exceptions
    and converts them into structured error results so the LLM always
    receives a valid response.

    Args:
        needs_sandbox: If True, lazily boots the sandbox before the tool runs.
            Use for tools that require sandbox access (bash, computer, browser, etc.).
    """

    def decorator(fn: Callable) -> Callable:
        is_coro = asyncio.iscoroutinefunction(fn)

        async def _invoke(*args: Any, **kwargs: Any) -> Any:
            if needs_sandbox:
                from nexus.tools._context import ensure_sandbox
                await ensure_sandbox()
            if is_coro:
                return await fn(*args, **kwargs)
            # Keep blocking I/O (E2B commands, screenshots) off the loop.
            return await asyncio.to_thread(fn, *args, **kwargs)

        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> NormalizedToolResult:
            from nexus.sandbox import SandboxDeadError

            try:
                result = await _invoke(*args, **kwargs)
                return _normalize(fn.__name__, result)
            except SandboxDeadError:
                if not needs_sandbox:
                    logger.exception("Tool %s failed", fn.__name__)
                    return tool_error(
                        f"Tool {fn.__name__} failed: sandbox is not running",
                        error_code="TOOL_EXCEPTION",
                        tool_name=fn.__name__,
                    )
                logger.warning(
                    "Sandbox died during %s — reconnecting and retrying once",
                    fn.__name__,
                )
                try:
                    result = await _invoke(*args, **kwargs)
                    return _normalize(fn.__name__, result)
                except SandboxDeadError as e:
                    logger.exception("Tool %s failed after sandbox reconnect", fn.__name__)
                    return tool_error(
                        f"Sandbox could not be restarted in this session: {e}",
                        error_code="SANDBOX_RECONNECT_FAILED",
                        retryable=True,
                        tool_name=fn.__name__,
                    )
                except Exception as e:
                    logger.exception("Tool %s failed", fn.__name__)
                    return tool_error(
                        f"Tool {fn.__name__} failed: {e}",
                        error_code="TOOL_EXCEPTION",
                        tool_name=fn.__name__,
                    )
            except Exception as e:
                logger.exception("Tool %s failed", fn.__name__)
                return tool_error(
                    f"Tool {fn.__name__} failed: {e}",
                    error_code="TOOL_EXCEPTION",
                    tool_name=fn.__name__,
                )

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> NormalizedToolResult:
            try:
                result = fn(*args, **kwargs)
                return _normalize(fn.__name__, result)
            except Exception as e:
                logger.exception("Tool %s failed", fn.__name__)
                return tool_error(
                    f"Tool {fn.__name__} failed: {e}",
                    error_code="TOOL_EXCEPTION",
                    tool_name=fn.__name__,
                )

        # Sandbox tools must be async so ensure_sandbox() runs before the body.
        if needs_sandbox or is_coro:
            return async_wrapper
        return sync_wrapper

    if func is not None:
        return decorator(func)
    return decorator


def _normalize(func_name: str, result: Any) -> NormalizedToolResult:
    """Convert any tool return value into a ``NormalizedToolResult``."""
    if isinstance(result, dict):
        # Already a NormalizedToolResult — fill in missing keys
        if "status" in result and "summary" in result:
            normalized = {
                "status": result.get("status", "success"),
                "summary": result.get("summary", ""),
                "detail": result.get("detail", result),
                "metadata": result.get("metadata", {}),
                "error_code": result.get("error_code", ""),
                "suggested_alternatives": result.get("suggested_alternatives", []),
                **({"retry_after": result["retry_after"]} if "retry_after" in result else {}),
            }
            if "retryable" in result:
                normalized["retryable"] = bool(result["retryable"])
            return normalized

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
