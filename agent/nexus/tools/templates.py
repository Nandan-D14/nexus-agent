# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Planner tools for proposing and editing workflow templates in chat."""

from __future__ import annotations

import json
import logging
from typing import Any

from nexus.history_models import StoredWorkflowTemplate
from nexus.tools._context import (
    get_history_repository,
    get_owner_id,
    get_send_json,
    get_session_id,
)
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


def _normalize_template_input_fields(raw: Any) -> list[dict[str, Any]]:
    """Reuse the router's normalizer without importing it at module load.

    ``nexus.routers.templates`` cannot be imported eagerly here: importing any
    submodule of ``nexus.routers`` runs its ``__init__``, which imports the ws
    router -> ws_handler -> orchestrator -> nexus.tools, and this module is part
    of that package. That cycle makes ``nexus.tools`` unimportable.
    """
    from nexus.routers.templates import (
        _normalize_template_input_fields as _normalize,
    )

    return _normalize(raw)


def _parse_input_fields(raw: Any) -> list[dict[str, Any]] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return _normalize_template_input_fields(raw)


def _template_payload(template: StoredWorkflowTemplate) -> dict[str, Any]:
    status = "draft" if getattr(template, "status", "published") == "draft" else "published"
    return {
        "type": "template_draft",
        "template_id": template.template_id,
        "status": status,
        "name": template.name,
        "description": template.description,
        "instructions": template.instructions,
        "input_fields": template.input_fields,
        "source_session_id": template.source_session_id,
    }


async def _emit_template_draft(template: StoredWorkflowTemplate) -> None:
    payload = _template_payload(template)
    send_json = get_send_json()
    if send_json:
        await send_json(payload)

    repo = get_history_repository()
    try:
        session_id = get_session_id()
    except RuntimeError:
        session_id = ""
    if repo and session_id:
        try:
            await repo.append_message(
                session_id=session_id,
                owner_id=get_owner_id(),
                role="tool_result",
                source="template_draft",
                text=json.dumps(payload),
            )
        except Exception:
            logger.warning(
                "Failed to persist template_draft for session %s",
                session_id,
            )


@normalized_tool
async def propose_workflow_template(
    name: str,
    instructions: str,
    description: str = "",
    input_fields: str = "[]",
) -> dict[str, Any]:
    """Create a reusable workflow template draft from this conversation.

    Use when the user asks to save this session as a template or clicks
    Create template. Persist a draft, then wait for the user to confirm,
    edit, or dismiss. Do not start a new session.

    Args:
        name: Short template title.
        instructions: The reusable process the agent should follow later.
        description: Optional one-line summary.
        input_fields: JSON array of {key, label, placeholder, required} objects
            collected each time the template is run. Use [] if none are needed.

    Returns:
        NormalizedToolResult with the draft template_id.
    """
    owner_id = get_owner_id()
    if not owner_id:
        return tool_error("No authenticated user in context.", error_code="AUTH_REQUIRED")
    repo = get_history_repository()
    if repo is None:
        return tool_error("Template storage is unavailable.", error_code="UNAVAILABLE")

    clean_name = (name or "").strip()[:80]
    clean_instructions = (instructions or "").strip()
    if not clean_name:
        return tool_error("Template name cannot be empty.", error_code="INVALID_INPUT")
    if not clean_instructions:
        return tool_error("Template instructions cannot be empty.", error_code="INVALID_INPUT")

    try:
        session_id = get_session_id()
    except RuntimeError:
        session_id = None

    fields = _parse_input_fields(input_fields) or []
    try:
        template = await repo.create_workflow_template(
            owner_id=owner_id,
            source_session_id=session_id,
            source_run_id=None,
            name=clean_name,
            description=(description or "").strip()[:240],
            instructions=clean_instructions,
            input_fields=fields,
            source_artifacts=[],
            status="draft",
        )
    except Exception as exc:
        logger.warning("propose_workflow_template failed", exc_info=True)
        return tool_error(f"Failed to create template: {exc}", error_code="TEMPLATE_WRITE_FAILED")

    await _emit_template_draft(template)
    return tool_success(
        f"Draft template '{template.name}' is ready for confirm, edit, or dismiss.",
        template_id=template.template_id,
        status="draft",
        name=template.name,
    )


@normalized_tool
async def update_workflow_template(
    template_id: str,
    name: str = "",
    description: str = "",
    instructions: str = "",
    input_fields: str = "",
) -> dict[str, Any]:
    """Update an existing workflow template owned by this user.

    Use when the user asks to change the in-chat template draft (rename,
    rewrite instructions, add or change input fields).

    Args:
        template_id: The template to update.
        name: New title, or empty to leave unchanged.
        description: New summary, or empty to leave unchanged.
        instructions: New process text, or empty to leave unchanged.
        input_fields: JSON array of fields, or empty to leave unchanged.

    Returns:
        NormalizedToolResult with the updated template.
    """
    owner_id = get_owner_id()
    if not owner_id:
        return tool_error("No authenticated user in context.", error_code="AUTH_REQUIRED")
    repo = get_history_repository()
    if repo is None:
        return tool_error("Template storage is unavailable.", error_code="UNAVAILABLE")

    clean_id = (template_id or "").strip()
    if not clean_id:
        return tool_error("template_id is required.", error_code="INVALID_INPUT")

    next_name = name.strip()[:80] if isinstance(name, str) and name.strip() else None
    next_description = (
        description.strip()[:240] if isinstance(description, str) and description.strip() else None
    )
    next_instructions = (
        instructions.strip() if isinstance(instructions, str) and instructions.strip() else None
    )
    next_fields = _parse_input_fields(input_fields) if input_fields not in (None, "") else None

    try:
        template = await repo.update_workflow_template(
            owner_id=owner_id,
            template_id=clean_id,
            name=next_name,
            description=next_description,
            instructions=next_instructions,
            input_fields=next_fields,
        )
    except Exception as exc:
        logger.warning("update_workflow_template failed", exc_info=True)
        return tool_error(f"Failed to update template: {exc}", error_code="TEMPLATE_WRITE_FAILED")

    if not template:
        return tool_error("Template not found.", error_code="NOT_FOUND")

    await _emit_template_draft(template)
    return tool_success(
        f"Updated template '{template.name}'.",
        template_id=template.template_id,
        status="draft" if template.status == "draft" else "published",
        name=template.name,
    )


@normalized_tool
async def publish_workflow_template(template_id: str) -> dict[str, Any]:
    """Publish a draft workflow template so it can be run later.

    Use when the user confirms the in-chat template card. Do not start a
    new session after publishing.

    Args:
        template_id: The draft to publish.

    Returns:
        NormalizedToolResult confirming the published template.
    """
    owner_id = get_owner_id()
    if not owner_id:
        return tool_error("No authenticated user in context.", error_code="AUTH_REQUIRED")
    repo = get_history_repository()
    if repo is None:
        return tool_error("Template storage is unavailable.", error_code="UNAVAILABLE")

    clean_id = (template_id or "").strip()
    if not clean_id:
        return tool_error("template_id is required.", error_code="INVALID_INPUT")

    current = await repo.get_workflow_template(owner_id, clean_id)
    if not current:
        return tool_error("Template not found.", error_code="NOT_FOUND")
    if not (current.name or "").strip() or not (current.instructions or "").strip():
        return tool_error(
            "A published template needs a name and instructions.",
            error_code="INVALID_INPUT",
        )

    try:
        template = await repo.update_workflow_template(
            owner_id=owner_id,
            template_id=clean_id,
            status="published",
        )
    except Exception as exc:
        logger.warning("publish_workflow_template failed", exc_info=True)
        return tool_error(f"Failed to publish template: {exc}", error_code="TEMPLATE_WRITE_FAILED")

    if not template:
        return tool_error("Template not found.", error_code="NOT_FOUND")

    await _emit_template_draft(template)
    return tool_success(
        f"Published template '{template.name}'. It is ready to run from Templates.",
        template_id=template.template_id,
        status="published",
        name=template.name,
    )
