# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Workflow templates endpoints."""

from __future__ import annotations

import re
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository, get_session_manager, get_session_create_limiter
from nexus.models import (
    CreateWorkflowTemplateRequest,
    RunWorkflowTemplateRequest,
    StatusMessage,
    UpdateWorkflowTemplateRequest,
    WorkflowTemplate,
    WorkflowTemplateInputField,
    WorkflowTemplateRunResponse,
)
from nexus.runtime_config import resolve_session_runtime_config
from nexus.sessions_helpers import _build_session_response, _prepare_user_runtime

router = APIRouter()

_TEMPLATE_KEY_RE = re.compile(r"[^a-z0-9_]+")

def _normalize_template_input_fields(
    fields: list[WorkflowTemplateInputField] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in fields or []:
        data = raw.model_dump() if isinstance(raw, WorkflowTemplateInputField) else raw
        if not isinstance(data, dict):
            continue
        base_key = data.get("key") if isinstance(data.get("key"), str) else ""
        candidate_key = _TEMPLATE_KEY_RE.sub("_", base_key.strip().lower()).strip("_")
        if not candidate_key:
            continue
        if candidate_key[0].isdigit():
            candidate_key = f"field_{candidate_key}"
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        label = data.get("label") if isinstance(data.get("label"), str) else ""
        placeholder = data.get("placeholder") if isinstance(data.get("placeholder"), str) else ""
        normalized.append(
            {
                "key": candidate_key[:40],
                "label": (label.strip() or candidate_key.replace("_", " ").title())[:80],
                "placeholder": placeholder.strip()[:120],
                "required": bool(data.get("required")),
            }
        )
    return normalized

def _serialize_workflow_template(template) -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id=template.template_id,
        owner_id=template.owner_id,
        name=template.name,
        description=template.description,
        source_session_id=template.source_session_id,
        source_run_id=template.source_run_id,
        instructions=template.instructions,
        input_fields=[
            WorkflowTemplateInputField.model_validate(field)
            for field in template.input_fields
        ],
        source_artifacts=template.source_artifacts,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_used_at=template.last_used_at,
    )

def _build_template_defaults(stored_session, run, steps, artifacts) -> dict[str, Any]:
    handoff = stored_session.handoff_summary or {}
    packet = stored_session.context_packet or {}

    summary = ""
    for candidate in (
        handoff.get("preview"),
        stored_session.summary,
        packet.get("summary"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            summary = candidate.strip()
            break

    goal = ""
    for candidate in (
        handoff.get("goal"),
        packet.get("goal"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            goal = candidate.strip()
            break

    latest_steps: list[str] = []
    for step in reversed(steps or []):
        if step.status != "completed":
            continue
        detail = (step.detail or step.title or "").strip()
        if detail and detail not in latest_steps:
            latest_steps.append(detail)
        if len(latest_steps) >= 3:
            break

    open_tasks = [
        str(item).strip()
        for item in (handoff.get("open_tasks") or packet.get("openTasks") or [])
        if str(item).strip()
    ][:3]
    source_artifacts = []
    for artifact in artifacts or []:
        candidate = (artifact.title or artifact.preview or artifact.kind or "").strip()
        if candidate and candidate not in source_artifacts:
            source_artifacts.append(candidate)
        if len(source_artifacts) >= 4:
            break

    if not (run or summary or goal or latest_steps or source_artifacts):
        raise HTTPException(
            status_code=400,
            detail="This session does not have enough saved context to become a template yet.",
        )

    name = (stored_session.title or "").strip() or handoff.get("headline") or "Workflow template"
    description = summary or goal or "Reusable workflow saved from a prior CoComputer session."

    instruction_lines = [
        "Use this saved CoComputer workflow as the execution pattern for the new task.",
    ]
    if goal:
        instruction_lines.append(f"Original goal: {goal}")
    if summary:
        instruction_lines.append(f"Saved summary: {summary}")
    if latest_steps:
        instruction_lines.append("Successful workflow steps to preserve:")
        instruction_lines.extend(f"- {item}" for item in latest_steps)
    if open_tasks:
        instruction_lines.append("Open tasks or follow-ups to consider:")
        instruction_lines.extend(f"- {item}" for item in open_tasks)
    if source_artifacts:
        instruction_lines.append("Reference artifacts from the source session:")
        instruction_lines.extend(f"- {item}" for item in source_artifacts)
    instruction_lines.append(
        "When this template is run, use the provided template input values and execute the workflow without asking the user to restate the saved context."
    )

    return {
        "name": name[:80],
        "description": description[:240],
        "instructions": "\n".join(instruction_lines).strip(),
        "source_artifacts": source_artifacts,
    }

async def _prepare_template_source(owner_id: str, session_id: str):
    history_repository = get_history_repository()
    stored_session = await history_repository.get_session(session_id)
    if not stored_session or stored_session.owner_id != owner_id or stored_session.status == "deleted":
        raise HTTPException(status_code=404, detail="Session not found")
    if not stored_session.handoff_summary or not stored_session.context_packet:
        await history_repository.refresh_session_handoff(session_id, owner_id=owner_id)
        stored_session = await history_repository.get_session(session_id)
        if not stored_session:
            raise HTTPException(status_code=404, detail="Session not found")
    run = await history_repository.get_session_run(session_id)
    steps = await history_repository.list_run_steps(session_id, run.run_id) if run else []
    artifacts = await history_repository.list_run_artifacts(session_id, run.run_id) if run else []
    return stored_session, run, steps, artifacts

def _build_template_prompt(template, inputs: dict[str, str]) -> str:
    normalized_inputs = {
        key.strip(): value.strip()
        for key, value in (inputs or {}).items()
        if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip()
    }
    field_lookup = {field["key"]: field for field in template.input_fields}
    missing_required = [
        field["label"]
        for field in template.input_fields
        if field.get("required") and not normalized_inputs.get(field["key"])
    ]
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required template inputs: {', '.join(missing_required)}",
        )

    lines = [template.instructions.strip()]
    if normalized_inputs:
        lines.append("")
        lines.append("Template inputs:")
        for field in template.input_fields:
            value = normalized_inputs.get(field["key"])
            if value:
                lines.append(f"- {field['label']}: {value}")
        for key in sorted(normalized_inputs):
            if key in field_lookup:
                continue
            lines.append(f"- {key}: {normalized_inputs[key]}")
    lines.append("")
    lines.append("Execute this workflow now using the saved process and the provided template inputs.")
    return "\n".join(part for part in lines if part is not None).strip()

async def _create_template_from_session_for_user(
    *,
    user: AuthenticatedUser,
    source_session_id: str,
    payload: CreateWorkflowTemplateRequest,
) -> WorkflowTemplate:
    history_repository = get_history_repository()
    stored_session, run, steps, artifacts = await _prepare_template_source(user.uid, source_session_id)
    defaults = _build_template_defaults(stored_session, run, steps, artifacts)
    normalized_input_fields = _normalize_template_input_fields(payload.input_fields)
    template = await history_repository.create_workflow_template(
        owner_id=user.uid,
        source_session_id=source_session_id,
        source_run_id=run.run_id if run else None,
        name=(payload.name or defaults["name"]).strip()[:80],
        description=(payload.description or defaults["description"]).strip()[:240],
        instructions=(payload.instructions or defaults["instructions"]).strip(),
        input_fields=normalized_input_fields,
        source_artifacts=defaults["source_artifacts"],
    )
    return _serialize_workflow_template(template)

@router.get("/api/v1/templates")
async def list_workflow_templates(
    limit: int = Query(100, ge=1, le=200),
    q: str | None = Query(None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    templates = await history_repository.list_workflow_templates(
        user.uid,
        limit=limit,
        search=q,
    )
    return {
        "templates": [
            _serialize_workflow_template(template).model_dump(mode="json")
            for template in templates
        ]
    }

@router.post("/api/v1/templates", response_model=WorkflowTemplate)
async def create_workflow_template(
    payload: CreateWorkflowTemplateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not payload.source_session_id:
        raise HTTPException(status_code=400, detail="source_session_id is required")
    return await _create_template_from_session_for_user(
        user=user,
        source_session_id=payload.source_session_id,
        payload=payload,
    )

@router.get("/api/v1/templates/{template_id}", response_model=WorkflowTemplate)
async def get_workflow_template(
    template_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    template = await history_repository.get_workflow_template(user.uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize_workflow_template(template)

@router.patch("/api/v1/templates/{template_id}", response_model=WorkflowTemplate)
async def update_workflow_template(
    template_id: str,
    payload: UpdateWorkflowTemplateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    name = payload.name.strip()[:80] if isinstance(payload.name, str) else None
    description = payload.description.strip()[:240] if isinstance(payload.description, str) else None
    instructions = payload.instructions.strip() if isinstance(payload.instructions, str) else None
    if payload.name is not None and not name:
        raise HTTPException(status_code=400, detail="Template name cannot be empty")
    if payload.instructions is not None and not instructions:
        raise HTTPException(status_code=400, detail="Template instructions cannot be empty")
    normalized_input_fields = (
        _normalize_template_input_fields(payload.input_fields)
        if payload.input_fields is not None
        else None
    )
    history_repository = get_history_repository()
    template = await history_repository.update_workflow_template(
        owner_id=user.uid,
        template_id=template_id,
        name=name,
        description=description,
        instructions=instructions,
        input_fields=normalized_input_fields,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize_workflow_template(template)

@router.delete("/api/v1/templates/{template_id}", response_model=StatusMessage)
async def delete_workflow_template(
    template_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    deleted = await history_repository.delete_workflow_template(user.uid, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return StatusMessage(status="deleted")

@router.post("/api/v1/templates/{template_id}/run", response_model=WorkflowTemplateRunResponse)
async def run_workflow_template(
    template_id: str,
    payload: RunWorkflowTemplateRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    session_create_limiter = get_session_create_limiter()
    if not session_create_limiter.check(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    history_repository = get_history_repository()
    template = await history_repository.get_workflow_template(user.uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    initial_prompt = _build_template_prompt(template, (payload or RunWorkflowTemplateRequest()).inputs)
    user_settings = await _prepare_user_runtime(user)
    session_manager = get_session_manager()
    try:
        session = await session_manager.create_session(
            owner_id=user.uid,
            runtime_config=resolve_session_runtime_config(user_settings),
            initial_title=template.name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    await history_repository.mark_workflow_template_used(user.uid, template_id)
    stored_session = await history_repository.get_session(session.id)
    ticket = session_manager.create_ticket(session.id, user.uid)
    return WorkflowTemplateRunResponse(
        session=_build_session_response(
            session=session,
            ticket=ticket,
            stored_session=stored_session,
        ),
        initial_prompt=initial_prompt,
    )

@router.post("/api/v1/sessions/{session_id}/template", response_model=WorkflowTemplate)
async def save_session_as_workflow_template(
    session_id: str,
    payload: CreateWorkflowTemplateRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    return await _create_template_from_session_for_user(
        user=user,
        source_session_id=session_id,
        payload=payload or CreateWorkflowTemplateRequest(),
    )
