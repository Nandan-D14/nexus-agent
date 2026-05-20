# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable task-state primitives for agentic workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

TaskType = Literal[
    "simple_answer",
    "code_task",
    "browser_task",
    "gui_task",
    "deep_research",
    "long_running_task",
    "general_task",
]
TaskStage = Literal[
    "intake",
    "planning",
    "delegating",
    "gathering_evidence",
    "synthesizing",
    "reviewing",
    "finalizing",
    "completed",
    "failed",
    "cancelled",
]
ReviewStatus = Literal[
    "not_required",
    "pending",
    "passed",
    "changes_requested",
    "failed",
]

TASK_TYPES: set[str] = set(TaskType.__args__)  # type: ignore[attr-defined]
TASK_STAGES: set[str] = set(TaskStage.__args__)  # type: ignore[attr-defined]
REVIEW_STATUSES: set[str] = set(ReviewStatus.__args__)  # type: ignore[attr-defined]

_DEEP_RESEARCH_TERMS = (
    "research",
    "investigate",
    "compare",
    "analysis",
    "analyze",
    "recommendation",
    "report",
    "deep dive",
    "multi-source",
    "sources",
)
_GUI_TERMS = (
    "click",
    "desktop",
    "screen",
    "screenshot",
    "gui",
    "window",
    "menu",
    "dialog",
    "drag",
    "type into",
    "open app",
)
_BROWSER_TERMS = (
    "browser",
    "website",
    "web",
    "search",
    "google",
    "look up",
    "open url",
    "login",
    "log in",
)
_CODE_TERMS = (
    "implement",
    "fix",
    "edit",
    "change",
    "update",
    "refactor",
    "build",
    "create",
    "generate",
    "write file",
    "run",
    "test",
    "install",
    "deploy",
    "repo",
    "code",
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_task_type(value: str | None) -> TaskType:
    candidate = str(value or "").strip()
    if candidate in TASK_TYPES:
        return candidate  # type: ignore[return-value]
    return "general_task"


def normalize_task_stage(value: str | None) -> TaskStage:
    candidate = str(value or "").strip()
    if candidate in TASK_STAGES:
        return candidate  # type: ignore[return-value]
    return "intake"


def normalize_review_status(value: str | None) -> ReviewStatus:
    candidate = str(value or "").strip()
    if candidate in REVIEW_STATUSES:
        return candidate  # type: ignore[return-value]
    return "not_required"


def infer_task_type(task_summary: str) -> TaskType:
    text = " ".join((task_summary or "").lower().split())
    if not text:
        return "general_task"
    if any(term in text for term in _DEEP_RESEARCH_TERMS):
        return "deep_research"
    if any(term in text for term in _GUI_TERMS):
        return "gui_task"
    if any(term in text for term in _CODE_TERMS):
        return "code_task"
    if any(term in text for term in _BROWSER_TERMS):
        return "browser_task"
    if len(text.split()) <= 24 and text.endswith("?"):
        return "simple_answer"
    return "general_task"


def build_initial_task_state(
    *,
    task_id: str,
    run_id: str,
    task_summary: str,
    task_type: str | None = None,
    active_agent: str = "nexus_orchestrator",
) -> dict[str, Any]:
    resolved_task_type = normalize_task_type(task_type) if task_type else infer_task_type(task_summary)
    now = utcnow_iso()
    return {
        "schema_version": 1,
        "task_id": task_id,
        "run_id": run_id,
        "task_type": resolved_task_type,
        "stage": "intake",
        "active_agent": active_agent or "nexus_orchestrator",
        "review_status": "pending" if resolved_task_type == "deep_research" else "not_required",
        "latest_request": task_summary.strip(),
        "todo": [],
        "evidence": [],
        "artifact_paths": [],
        "trace": [
            {
                "timestamp": now,
                "event": "task_state_initialized",
                "agent": active_agent or "nexus_orchestrator",
                "stage": "intake",
                "summary": task_summary.strip(),
            }
        ],
        "created_at": now,
        "updated_at": now,
    }


def refresh_task_state_for_request(
    state: dict[str, Any],
    *,
    task_id: str,
    run_id: str,
    task_summary: str,
    task_type: str | None = None,
    active_agent: str = "nexus_orchestrator",
) -> dict[str, Any]:
    if not isinstance(state, dict) or not state:
        return build_initial_task_state(
            task_id=task_id,
            run_id=run_id,
            task_summary=task_summary,
            task_type=task_type,
            active_agent=active_agent,
        )

    resolved_type = normalize_task_type(task_type) if task_type else infer_task_type(task_summary)
    updated = dict(state)
    updated.setdefault("schema_version", 1)
    updated["task_id"] = task_id
    updated["run_id"] = run_id
    updated["task_type"] = resolved_type
    updated["stage"] = "intake"
    updated["active_agent"] = active_agent or "nexus_orchestrator"
    updated["review_status"] = "pending" if resolved_type == "deep_research" else "not_required"
    updated["latest_request"] = task_summary.strip()
    updated.setdefault("todo", [])
    updated.setdefault("evidence", [])
    updated.setdefault("artifact_paths", [])
    updated.setdefault("created_at", utcnow_iso())
    updated["updated_at"] = utcnow_iso()
    trace = list(updated.get("trace") or [])
    trace.append(
        {
            "timestamp": updated["updated_at"],
            "event": "task_state_refreshed",
            "agent": active_agent or "nexus_orchestrator",
            "stage": "intake",
            "summary": task_summary.strip(),
        }
    )
    updated["trace"] = trace[-100:]
    return updated


def merge_task_state(
    state: dict[str, Any],
    *,
    stage: str | None = None,
    active_agent: str | None = None,
    review_status: str | None = None,
    todo: list[str] | None = None,
    evidence: list[str] | None = None,
    artifact_paths: list[str] | None = None,
    event: str = "task_state_updated",
    summary: str = "",
) -> dict[str, Any]:
    updated = dict(state or {})
    updated.setdefault("schema_version", 1)
    updated.setdefault("task_id", "")
    updated.setdefault("run_id", "")
    updated.setdefault("task_type", "general_task")
    updated.setdefault("stage", "intake")
    updated.setdefault("active_agent", "nexus_orchestrator")
    updated.setdefault("review_status", "not_required")
    updated.setdefault("latest_request", "")
    updated.setdefault("todo", [])
    updated.setdefault("evidence", [])
    updated.setdefault("artifact_paths", [])
    updated.setdefault("created_at", utcnow_iso())

    if stage is not None:
        updated["stage"] = normalize_task_stage(stage)
    if active_agent is not None:
        updated["active_agent"] = str(active_agent or "").strip() or updated["active_agent"]
    if review_status is not None:
        updated["review_status"] = normalize_review_status(review_status)
    if todo is not None:
        updated["todo"] = [str(item).strip() for item in todo if str(item).strip()]
    if evidence:
        existing_evidence = [str(item) for item in updated.get("evidence") or []]
        for item in evidence:
            cleaned = str(item).strip()
            if cleaned and cleaned not in existing_evidence:
                existing_evidence.append(cleaned)
        updated["evidence"] = existing_evidence[-200:]
    if artifact_paths:
        existing_paths = [str(item) for item in updated.get("artifact_paths") or []]
        for item in artifact_paths:
            cleaned = str(item).strip()
            if cleaned and cleaned not in existing_paths:
                existing_paths.append(cleaned)
        updated["artifact_paths"] = existing_paths[-100:]

    updated["updated_at"] = utcnow_iso()
    trace = list(updated.get("trace") or [])
    trace.append(
        {
            "timestamp": updated["updated_at"],
            "event": event or "task_state_updated",
            "agent": updated.get("active_agent", "nexus_orchestrator"),
            "stage": updated.get("stage", "intake"),
            "summary": summary.strip(),
        }
    )
    updated["trace"] = trace[-100:]
    return updated
