# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Skill-reading tools for dynamic, on-demand instructions."""

from __future__ import annotations

from typing import Any

from nexus.skills import list_agent_skills
from nexus.tools._context import get_history_repository, get_owner_id
from nexus.tools.base import normalized_tool, tool_error, tool_success


async def _load_user_settings() -> dict[str, Any] | None:
    repository = get_history_repository()
    owner_id = get_owner_id()
    if repository is None or not owner_id:
        return None
    return await repository.get_user_settings(owner_id)


@normalized_tool
async def read_skill(skill_id: str) -> dict[str, Any]:
    """Load full instructions for one enabled CoComputer skill.

    Use after scanning the skill catalog in the prompt. Disabled or unknown
    skills are rejected so the model cannot bypass per-user settings.
    """
    target = str(skill_id or "").strip()
    if not target:
        return tool_error("skill_id is required.", error_code="INVALID_SKILL_ID")

    try:
        user_settings = await _load_user_settings()
    except Exception:
        return tool_error(
            "Could not load user skill settings.",
            error_code="SKILL_SETTINGS_UNAVAILABLE",
        )

    for skill in list_agent_skills(user_settings):
        if skill.get("skill_id") != target:
            continue
        if not skill.get("enabled"):
            return tool_error(
                f"Skill {target} is disabled.",
                error_code="SKILL_DISABLED",
                skill_id=target,
            )
        return tool_success(
            f"Loaded skill {skill.get('name') or target}.",
            skill_id=target,
            name=skill.get("name"),
            category=skill.get("category"),
            description=skill.get("description"),
            trigger=skill.get("trigger"),
            instructions=skill.get("instructions") or "",
            source=skill.get("source"),
            agent_scope=skill.get("agent_scope") or [],
        )

    return tool_error(
        f"Skill {target} was not found.",
        error_code="SKILL_NOT_FOUND",
        skill_id=target,
    )
