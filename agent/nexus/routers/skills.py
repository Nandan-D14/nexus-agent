# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Agent skills management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository
from nexus.models import AgentSkillUpsertRequest, StatusMessage
from nexus.skills import build_agent_skills_update, list_agent_skills, _custom_skill, _now_iso

router = APIRouter()
history_repository = get_history_repository()

@router.get("/api/v1/skills")
async def list_skills(user: AuthenticatedUser = Depends(require_current_user)):
    user_settings = await history_repository.get_user_settings(user.uid)
    skills = list_agent_skills(user_settings)
    return {"skills": skills}

@router.post("/api/v1/skills")
async def create_skill(
    payload: AgentSkillUpsertRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not payload.name or not payload.instructions:
        raise HTTPException(status_code=400, detail="Skill name and instructions are required.")
    user_settings = await history_repository.get_user_settings(user.uid)
    state = build_agent_skills_update(user_settings)["agentSkills"]
    custom = list(state.get("custom") or [])

    skill = _custom_skill(
        {
            "name": payload.name,
            "category": payload.category or "Custom",
            "description": payload.description or "",
            "trigger": payload.trigger or "",
            "instructions": payload.instructions,
            "enabled": payload.enabled if payload.enabled is not None else True,
        }
    )
    if not skill:
        raise HTTPException(status_code=400, detail="Invalid skill payload.")
    custom.append(skill)
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=custom),
    )
    return {"skill": skill}

@router.patch("/api/v1/skills/{skill_id}")
async def update_skill(
    skill_id: str,
    payload: AgentSkillUpsertRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    skills = list_agent_skills(user_settings)
    existing = next((skill for skill in skills if skill["skill_id"] == skill_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Skill not found")

    state = build_agent_skills_update(user_settings)["agentSkills"]
    disabled_defaults = set(state.get("disabledDefaults") or [])
    custom = list(state.get("custom") or [])

    if existing["source"] == "built_in":
        if payload.enabled is True:
            disabled_defaults.discard(skill_id)
        elif payload.enabled is False:
            disabled_defaults.add(skill_id)
        await history_repository.update_user_settings(
            user.uid,
            build_agent_skills_update(user_settings, disabled_defaults=disabled_defaults),
        )
        updated = next(skill for skill in list_agent_skills(await history_repository.get_user_settings(user.uid)) if skill["skill_id"] == skill_id)
        return {"skill": updated}

    updated_custom = []
    updated = None

    for skill in custom:
        if skill.get("skill_id") != skill_id:
            updated_custom.append(skill)
            continue
        candidate = {
            **skill,
            "name": payload.name if payload.name is not None else skill.get("name"),
            "category": payload.category if payload.category is not None else skill.get("category"),
            "description": payload.description if payload.description is not None else skill.get("description"),
            "trigger": payload.trigger if payload.trigger is not None else skill.get("trigger"),
            "instructions": payload.instructions if payload.instructions is not None else skill.get("instructions"),
            "enabled": payload.enabled if payload.enabled is not None else skill.get("enabled", True),
            "updated_at": _now_iso(),
        }
        updated = _custom_skill(candidate)
        if updated:
            updated_custom.append(updated)
    if not updated:
        raise HTTPException(status_code=400, detail="Invalid skill update.")
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=updated_custom),
    )
    return {"skill": updated}

@router.delete("/api/v1/skills/{skill_id}", response_model=StatusMessage)
async def delete_skill(
    skill_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    state = build_agent_skills_update(user_settings)["agentSkills"]
    custom = [skill for skill in (state.get("custom") or []) if skill.get("skill_id") != skill_id]
    if len(custom) == len(state.get("custom") or []):
        raise HTTPException(status_code=404, detail="Only user-created skills can be deleted.")
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=custom),
    )
    return StatusMessage(status="deleted")
