# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Memory tools — let the agent persist and recall durable user facts."""

from __future__ import annotations

import logging
from typing import Any

from nexus.config import settings
from nexus.memory import get_memory_store
from nexus.tools._context import get_owner_id, get_session_id
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


@normalized_tool
async def remember_fact(fact: str, category: str = "general") -> dict[str, Any]:
    """Save one durable fact about the user or their ongoing projects.

    Use when the user states a lasting preference, constraint, or project
    detail worth remembering across sessions (e.g. "I deploy on Cloud Run",
    "always answer in Spanish", "my startup is called Acme"). Do NOT save
    one-off task details, secrets, or anything the user asked to keep private.

    Args:
        fact: One short sentence stating the fact.
        category: Optional label like "preference", "project", "profile".

    Returns:
        NormalizedToolResult confirming the saved fact.
    """
    if not settings.memory_enabled:
        return tool_error("Memory is disabled.", error_code="MEMORY_DISABLED")
    owner_id = get_owner_id()
    if not owner_id:
        return tool_error("No authenticated user in context.", error_code="AUTH_REQUIRED")
    cleaned = " ".join(str(fact or "").split())
    if not cleaned:
        return tool_error("fact is required", error_code="INVALID_INPUT")

    try:
        session_id = get_session_id()
    except Exception:
        session_id = None

    try:
        saved = await get_memory_store().add_fact(
            owner_id=owner_id,
            text=cleaned,
            category=category,
            session_id=session_id,
        )
    except Exception as exc:
        logger.warning("remember_fact failed", exc_info=True)
        return tool_error(f"Failed to save memory: {exc}", error_code="MEMORY_WRITE_FAILED")

    return tool_success(
        f"Remembered: {saved.text}",
        fact_id=saved.fact_id,
        category=saved.category,
    )


@normalized_tool
async def recall_facts(limit: int = 10) -> dict[str, Any]:
    """List durable facts previously saved about this user.

    Recent facts are already injected into your context automatically; use
    this only when you need more than what was injected.

    Args:
        limit: Maximum number of facts to return (most recent first).

    Returns:
        NormalizedToolResult with the stored facts.
    """
    if not settings.memory_enabled:
        return tool_error("Memory is disabled.", error_code="MEMORY_DISABLED")
    owner_id = get_owner_id()
    if not owner_id:
        return tool_error("No authenticated user in context.", error_code="AUTH_REQUIRED")

    try:
        facts = await get_memory_store().list_facts(
            owner_id=owner_id,
            limit=max(1, min(int(limit or 10), 50)),
        )
    except Exception as exc:
        logger.warning("recall_facts failed", exc_info=True)
        return tool_error(f"Failed to read memory: {exc}", error_code="MEMORY_READ_FAILED")

    return tool_success(
        f"Found {len(facts)} stored fact(s).",
        facts=[
            {
                "fact_id": item.fact_id,
                "text": item.text,
                "category": item.category,
                "created_at": item.created_at.isoformat(),
            }
            for item in facts
        ],
    )
