# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Base utilities for tools, including normalization decorators."""

from __future__ import annotations

import asyncio
from functools import wraps
import logging
from typing import Any, Callable, TypedDict

logger = logging.getLogger(__name__)

class NormalizedToolResult(TypedDict):
    status: str
    summary: str
    detail: Any
    metadata: dict[str, Any]

def normalized_tool(func: Callable) -> Callable:
    """Decorator to normalize tool outputs into a standard schema."""
    @wraps(func)
    async def async_wrapper(*args, **kwargs) -> NormalizedToolResult:
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return _normalize(func.__name__, result)
        except Exception as e:
            logger.exception("Tool %s failed", func.__name__)
            return {
                "status": "error",
                "summary": f"Tool {func.__name__} failed: {str(e)}",
                "detail": str(e),
                "metadata": {}
            }

    @wraps(func)
    def sync_wrapper(*args, **kwargs) -> NormalizedToolResult:
        try:
            result = func(*args, **kwargs)
            return _normalize(func.__name__, result)
        except Exception as e:
            logger.exception("Tool %s failed", func.__name__)
            return {
                "status": "error",
                "summary": f"Tool {func.__name__} failed: {str(e)}",
                "detail": str(e),
                "metadata": {}
            }

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

def _normalize(func_name: str, result: Any) -> NormalizedToolResult:
    if isinstance(result, dict) and "status" in result and "summary" in result:
        # Ensure it has all required keys
        return {
            "status": result.get("status", "success"),
            "summary": result.get("summary", ""),
            "detail": result.get("detail", result),
            "metadata": result.get("metadata", {k: v for k, v in result.items() if k not in ["status", "summary", "detail"]})
        }

    status = "success"
    summary = ""
    detail = result
    metadata = {}

    if isinstance(result, dict):
        if "error" in result:
            status = "error"
            summary = result["error"]
        elif "summary" in result:
            summary = result["summary"]
        elif "description" in result:
            summary = result["description"]
        
        # Heuristic: if it's a dict, move keys to metadata if they are not the main result
        metadata = {k: v for k, v in result.items() if k not in ["summary", "status", "error", "detail"]}
    
    return {
        "status": status,
        "summary": summary or f"Executed {func_name}",
        "detail": detail,
        "metadata": metadata
    }
