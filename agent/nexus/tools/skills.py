# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Skill-reading tools for progressive disclosure (catalog → SKILL.md → files)."""

from __future__ import annotations

from typing import Any

from nexus.skill_format import SKILL_MD_FILENAME, render_skill_md, safe_skill_relpath
from nexus.skills import get_agent_skill
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

    skill = get_agent_skill(user_settings, target, include_files=True)
    if skill is None:
        return tool_error(
            f"Skill {target} was not found.",
            error_code="SKILL_NOT_FOUND",
            skill_id=target,
        )
    if not skill.get("enabled"):
        return tool_error(
            f"Skill {target} is disabled.",
            error_code="SKILL_DISABLED",
            skill_id=target,
        )
    resources = list(skill.get("resources") or sorted(skill.get("files") or {}))
    sandbox_path = skill.get("sandbox_path") or ""
    return tool_success(
        f"Loaded skill {skill.get('name') or target}.",
        skill_id=target,
        name=skill.get("name"),
        category=skill.get("category"),
        description=skill.get("description"),
        trigger=skill.get("trigger"),
        instructions=skill.get("instructions") or "",
        source=skill.get("source"),
        format=skill.get("format") or "legacy",
        agent_scope=skill.get("agent_scope") or [],
        resources=resources,
        sandbox_path=sandbox_path,
        license=skill.get("license") or "",
        hint=(
            f"Call read_skill_file('{target}', path) for resources. Sandbox copy: {sandbox_path}/"
            if resources
            else ""
        ),
    )


@normalized_tool
async def read_skill_file(skill_id: str, path: str) -> dict[str, Any]:
    """Load one file from an enabled skill package (progressive disclosure).

    Use after read_skill lists resources. Path is relative to the skill root
    (for example references/checklist.md or scripts/csv_preview.py).
    Pass SKILL.md to get the portable Agent Skills document.
    """
    target = str(skill_id or "").strip()
    rel = safe_skill_relpath(path)
    if not target:
        return tool_error("skill_id is required.", error_code="INVALID_SKILL_ID")
    if not rel:
        return tool_error("path is invalid.", error_code="INVALID_SKILL_PATH", skill_id=target)

    try:
        user_settings = await _load_user_settings()
    except Exception:
        return tool_error(
            "Could not load user skill settings.",
            error_code="SKILL_SETTINGS_UNAVAILABLE",
        )

    skill = get_agent_skill(user_settings, target, include_files=True)
    if skill is None:
        return tool_error(
            f"Skill {target} was not found.",
            error_code="SKILL_NOT_FOUND",
            skill_id=target,
        )
    if not skill.get("enabled"):
        return tool_error(
            f"Skill {target} is disabled.",
            error_code="SKILL_DISABLED",
            skill_id=target,
        )

    if rel == SKILL_MD_FILENAME:
        return tool_success(
            f"Loaded {SKILL_MD_FILENAME} for {target}.",
            skill_id=target,
            path=SKILL_MD_FILENAME,
            content=render_skill_md(skill),
        )

    files = skill.get("files") or {}
    if rel not in files:
        return tool_error(
            f"Skill file {rel} was not found.",
            error_code="SKILL_FILE_NOT_FOUND",
            skill_id=target,
            path=rel,
            resources=sorted(files),
        )
    return tool_success(
        f"Loaded {rel} from skill {target}.",
        skill_id=target,
        path=rel,
        content=files[rel],
    )


read_skill = read_skill
read_skill_file = read_skill_file
