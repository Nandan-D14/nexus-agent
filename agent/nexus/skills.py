# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Agent skill registry and prompt helpers."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from nexus.bundled_skill_files import BUNDLED_SKILL_FILES
from nexus.skill_format import ParsedSkill, normalize_skill_files, skill_sandbox_path


DEFAULT_AGENT_SKILLS: list[dict[str, Any]] = [
    {
        "skill_id": "browser-research",
        "name": "Browser Research",
        "category": "Research",
        "description": "Search the web, read sources, and collect citations.",
        "trigger": "Use for web research, current facts, docs, and source-backed answers.",
        "instructions": "Gather evidence from reliable sources and summarize with source links.",
        "agent_scope": ["nexus_planner", "desktop_worker", "researcher"],
    },
    {
        "skill_id": "web-automation",
        "name": "Web Automation",
        "category": "Browser",
        "description": "Navigate sites, forms, and browser workflows.",
        "trigger": "Use when the task requires web pages, forms, logins, or browser-only UI.",
        "instructions": "Use browser tools for navigation and keep user credentials scoped.",
        "agent_scope": ["nexus_planner", "desktop_worker"],
    },
    {
        "skill_id": "codebase-engineering",
        "name": "Codebase Engineering",
        "category": "Coding",
        "description": "Inspect repos, edit files, run tests, and fix bugs.",
        "trigger": "Use for code changes, debugging, refactors, tests, and repo analysis.",
        "instructions": "Read the code first, keep edits scoped, and verify with relevant commands.",
        "agent_scope": ["nexus_planner", "terminal_worker", "coder"],
    },
    {
        "skill_id": "terminal-ops",
        "name": "Terminal Operations",
        "category": "System",
        "description": "Run shell commands, scripts, package tools, and process checks.",
        "trigger": "Use for CLI tasks, environment checks, logs, installs, and command output.",
        "instructions": "Prefer precise commands, avoid destructive actions, and report key output.",
        "agent_scope": ["nexus_planner", "terminal_worker", "coder"],
    },
    {
        "skill_id": "desktop-control",
        "name": "Desktop Control",
        "category": "Computer",
        "description": "Interact with GUI apps, screenshots, menus, and dialogs.",
        "trigger": "Use for visible desktop state, native apps, file pickers, and mouse/keyboard work.",
        "instructions": "Use computer control only when visual GUI interaction is required.",
        "agent_scope": ["nexus_planner", "desktop_worker"],
    },
    {
        "skill_id": "workspace-files",
        "name": "Workspace Files",
        "category": "Files",
        "description": "Create, read, and organize workspace artifacts.",
        "trigger": "Use when the task needs files, reports, exports, or saved artifacts.",
        "instructions": "Create durable files in the session workspace and name outputs clearly.",
        "agent_scope": [
            "nexus_planner",
            "terminal_worker",
            "desktop_worker",
            "researcher",
            "coder",
            "writer",
        ],
    },
    {
        "skill_id": "data-analysis",
        "name": "Data Analysis",
        "category": "Analysis",
        "description": "Analyze CSV, JSON, logs, metrics, and structured data.",
        "trigger": "Use for calculations, comparisons, charts, metrics, and dataset summaries.",
        "instructions": "Use structured parsing where possible and explain assumptions.",
        "agent_scope": ["nexus_planner", "terminal_worker", "coder", "researcher"],
    },
    {
        "skill_id": "spreadsheet-work",
        "name": "Spreadsheet Work",
        "category": "Documents",
        "description": "Create and edit spreadsheets, formulas, tables, and charts.",
        "trigger": "Use for XLSX/CSV work, financial tables, formulas, and spreadsheet exports.",
        "instructions": (
            "Build the table in structured data first, then export.\n"
            "1. Confirm columns, units, and the output filename.\n"
            "2. Preview CSV sources with scripts/csv_preview.py in this skill folder "
            "(`/home/user/skills/spreadsheet-work/scripts/csv_preview.py`) when the sandbox is up.\n"
            "3. Use generate_excel_report for XLSX deliverables; keep formulas/notes explicit.\n"
            "4. Read references/sheet-checklist.md before finishing.\n"
            "Call read_skill_file for resource files instead of guessing their contents."
        ),
        "agent_scope": ["nexus_planner", "terminal_worker", "desktop_worker"],
    },
    {
        "skill_id": "document-work",
        "name": "Document Work",
        "category": "Documents",
        "description": "Draft, edit, summarize, and format documents.",
        "trigger": "Use for DOCX, Markdown, reports, summaries, and written deliverables.",
        "instructions": (
            "Draft in Markdown, then convert to the requested format.\n"
            "1. Confirm audience, filename, and whether the output is PDF, DOCX, or Markdown.\n"
            "2. Outline headings, then write the body.\n"
            "3. Convert with generate_pdf_report or generate_docx_report; never invent file bytes.\n"
            "4. Save with save_as_artifact. Read references/deliverable-checklist.md before finishing.\n"
            "Skill files mount at `/home/user/skills/document-work/`. "
            "Call read_skill_file(skill_id, path) for bundled resources."
        ),
        "agent_scope": ["nexus_planner", "terminal_worker", "writer", "researcher"],
    },
    {
        "skill_id": "presentation-work",
        "name": "Presentation Work",
        "category": "Documents",
        "description": "Create slide decks, outlines, and presentation content.",
        "trigger": "Use for PPTX, slide plans, pitch decks, and visual summaries.",
        "instructions": (
            "Keep slides scannable and organize content into strong sections.\n"
            "1. Confirm audience, filename, and slide count before generating.\n"
            "2. Outline each slide as a title plus short bullets.\n"
            "3. Call generate_pptx_report(title, slides=[{title, bullets}], filename) "
            "instead of inventing PPTX bytes. The tool also emits an HTML preview for Canvas.\n"
            "4. Save extra supporting files with save_as_artifact if needed."
        ),
        "agent_scope": ["nexus_planner", "terminal_worker", "desktop_worker", "writer"],
    },
    {
        "skill_id": "github-review",
        "name": "GitHub Review",
        "category": "Developer",
        "description": "Review PRs, issues, diffs, and repository changes.",
        "trigger": "Use for GitHub issues, pull requests, code review, and CI context.",
        "instructions": (
            "Review the diff, not the vibe.\n"
            "1. Identify the PR/issue and the claimed intent.\n"
            "2. Use github_summarize_pr / github_read_file / github_list_issues when connected.\n"
            "3. Report blocking issues first (correctness, security, tests), then nits.\n"
            "4. Quote file paths. Read references/review-checklist.md before the final summary.\n"
            "Call read_skill_file for bundled resources."
        ),
        "agent_scope": ["nexus_planner", "terminal_worker", "coder", "researcher"],
    },
    {
        "skill_id": "qa-testing",
        "name": "QA Testing",
        "category": "Testing",
        "description": "Run checks, inspect failures, and verify app behavior.",
        "trigger": "Use for test plans, smoke tests, failing tests, and validation.",
        "instructions": "Prefer targeted verification first, then broader checks when risk is high.",
        "agent_scope": ["nexus_planner", "terminal_worker", "desktop_worker", "coder"],
    },
    {
        "skill_id": "mcp-tool-use",
        "name": "MCP Tool Use",
        "category": "Tools",
        "description": "Use enabled MCP connectors and remote tool servers.",
        "trigger": "Use when external MCP tools are selected or clearly useful.",
        "instructions": "Choose the smallest useful external tool and request permission for risky actions.",
        "agent_scope": ["nexus_planner", "terminal_worker", "desktop_worker"],
    },
    {
        "skill_id": "email-calendar",
        "name": "Email and Calendar",
        "category": "Productivity",
        "description": "Work with Gmail, Calendar, Tasks, and Drive when connected.",
        "trigger": "Use for email search/send, calendar events, tasks, and Drive files.",
        "instructions": (
            "Use native tools when Google is connected: gmail_search/gmail_read/gmail_send, "
            "calendar_list/calendar_get/calendar_create/calendar_update/calendar_delete "
            "(include time_zone and optional attendees; list with time_min/time_max for a day), "
            "and tasks_list/tasks_create. Do not open Gmail or Calendar in the browser "
            "or ask the user to sign in when those tools are available. Confirm recipients, "
            "dates, and irreversible sends; creates, updates, and deletes require user approval."
        ),
        "agent_scope": ["nexus_planner", "desktop_worker", "terminal_worker"],
    },
    {
        "skill_id": "workflow-templates",
        "name": "Workflow Templates",
        "category": "Automation",
        "description": "Reuse saved task workflows and repeatable operating procedures.",
        "trigger": "Use when a task matches a saved workflow or should become repeatable.",
        "instructions": (
            "When the user wants to save this conversation as a reusable workflow, "
            "call propose_workflow_template with a name, instructions, and input fields, "
            "then wait for confirm, edit, or dismiss. Use update_workflow_template for "
            "requested changes and publish_workflow_template only after they confirm. "
            "Do not start a new session. When running an already published template, "
            "follow the saved process and adapt only the user-provided inputs."
        ),
        "agent_scope": ["nexus_planner"],
    },
]


_V2_AGENT_SCOPE_ALIASES: dict[str, tuple[str, ...]] = {
    "nexus": ("nexus_planner",),
    "nexus_orchestrator": ("nexus_planner",),
    "code_agent": ("terminal_worker",),
    "research_code_agent": ("terminal_worker", "coder"),
    "browser_agent": ("desktop_worker",),
    "research_browser_agent": ("desktop_worker", "researcher"),
    "computer_agent": ("desktop_worker",),
    "research_computer_agent": ("desktop_worker",),
    "deepresearcher": ("nexus_planner", "researcher"),
    "research_reviewer_agent": ("nexus_planner", "writer"),
}


def _expand_default_skill_scopes(skill: dict[str, Any]) -> dict[str, Any]:
    scope = skill.get("agent_scope")
    if not isinstance(scope, list):
        return skill
    expanded = list(scope)
    seen = set(expanded)
    for legacy_name, aliases in _V2_AGENT_SCOPE_ALIASES.items():
        if legacy_name not in seen:
            continue
        for alias in aliases:
            if alias not in seen:
                expanded.append(alias)
                seen.add(alias)
    return {**skill, "agent_scope": expanded}


DEFAULT_AGENT_SKILLS = [
    _expand_default_skill_scopes(skill)
    for skill in DEFAULT_AGENT_SKILLS
]


def _attach_bundled_skill_files() -> None:
    for skill in DEFAULT_AGENT_SKILLS:
        files = BUNDLED_SKILL_FILES.get(str(skill.get("skill_id") or ""))
        if not files:
            continue
        skill["files"] = dict(files)
        skill["format"] = "agent_skill"


_attach_bundled_skill_files()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, fallback: str = "skill") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:60] or fallback


def _default_skill(raw: dict[str, Any]) -> dict[str, Any]:
    files = normalize_skill_files(raw.get("files"))
    return {
        **raw,
        "source": "built_in",
        "enabled": True,
        "created_at": None,
        "updated_at": None,
        "format": raw.get("format") or ("agent_skill" if files else "legacy"),
        "files": files,
        "license": str(raw.get("license") or ""),
        "compatibility": str(raw.get("compatibility") or ""),
        "allowed_tools": str(raw.get("allowed_tools") or ""),
        "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
    }


def _custom_skill(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    instructions = str(raw.get("instructions") or "").strip() or str(raw.get("description") or "").strip()
    if not name or not instructions:
        return None
    skill_id = str(raw.get("skill_id") or raw.get("id") or "").strip()
    if not skill_id:
        skill_id = f"user-{_slug(name)}-{uuid.uuid4().hex[:6]}"
    files = normalize_skill_files(raw.get("files"))
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return {
        "skill_id": skill_id[:96],
        "name": name[:80],
        "category": str(raw.get("category") or "Custom").strip()[:40] or "Custom",
        "description": str(raw.get("description") or "").strip()[:1024],
        "trigger": str(raw.get("trigger") or "").strip()[:500],
        "instructions": instructions[:16000],
        "source": "user",
        "enabled": bool(raw.get("enabled", True)),
        "created_at": raw.get("created_at") or _now_iso(),
        "updated_at": raw.get("updated_at") or _now_iso(),
        "format": "agent_skill" if raw.get("format") == "agent_skill" or files else "legacy",
        "files": files,
        "license": str(raw.get("license") or "")[:200],
        "compatibility": str(raw.get("compatibility") or "")[:500],
        "allowed_tools": str(raw.get("allowed_tools") or "")[:500],
        "metadata": {str(key): str(val) for key, val in metadata.items()},
    }


def _finalize_skill(skill: dict[str, Any], *, include_files: bool) -> dict[str, Any]:
    files = normalize_skill_files(skill.get("files"))
    out = {
        **skill,
        "files": files,
        "format": skill.get("format") or ("agent_skill" if files else "legacy"),
        "resources": sorted(files),
        "sandbox_path": skill_sandbox_path(str(skill.get("skill_id") or "skill")),
        "license": str(skill.get("license") or ""),
        "compatibility": str(skill.get("compatibility") or ""),
        "allowed_tools": str(skill.get("allowed_tools") or ""),
        "metadata": skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {},
    }
    if not include_files:
        out.pop("files", None)
    return out


def public_skill(skill: dict[str, Any]) -> dict[str, Any]:
    return _finalize_skill(skill, include_files=False)


def _clip_prompt_text(value: Any, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def get_agent_skill_state(user_settings: dict[str, Any] | None) -> dict[str, Any]:
    state = (user_settings or {}).get("agentSkills")
    return state if isinstance(state, dict) else {}


def list_agent_skills(
    user_settings: dict[str, Any] | None,
    *,
    include_files: bool = True,
) -> list[dict[str, Any]]:
    state = get_agent_skill_state(user_settings)
    disabled_defaults = set(state.get("disabledDefaults") or [])
    defaults = [
        {**_default_skill(skill), "enabled": skill["skill_id"] not in disabled_defaults}
        for skill in DEFAULT_AGENT_SKILLS
    ]
    custom = [
        skill
        for raw in (state.get("custom") or [])
        if (skill := _custom_skill(raw))
    ]
    custom_by_id = {skill["skill_id"]: skill for skill in custom}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill in defaults:
        skill_id = skill["skill_id"]
        merged = custom_by_id.get(skill_id, skill)
        if skill_id in custom_by_id:
            merged = {**merged, "enabled": custom_by_id[skill_id].get("enabled", True)}
        result.append(_finalize_skill(merged, include_files=include_files))
        seen.add(skill_id)
    for skill in custom:
        if skill["skill_id"] not in seen:
            result.append(_finalize_skill(skill, include_files=include_files))
    return result


def get_agent_skill(
    user_settings: dict[str, Any] | None,
    skill_id: str,
    *,
    include_files: bool = True,
) -> dict[str, Any] | None:
    target = str(skill_id or "").strip()
    if not target:
        return None
    for skill in list_agent_skills(user_settings, include_files=include_files):
        if skill.get("skill_id") == target:
            return skill
    return None


def skill_from_parsed(
    parsed: ParsedSkill,
    *,
    files: dict[str, str] | None = None,
    enabled: bool = True,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    display_name = parsed.name.replace("-", " ").title()
    payload = {
        **(existing or {}),
        "skill_id": parsed.name,
        "name": display_name[:80],
        "category": parsed.category[:40],
        "description": parsed.description,
        "trigger": parsed.trigger,
        "instructions": parsed.body or parsed.description,
        "enabled": enabled,
        "format": "agent_skill",
        "license": parsed.license,
        "compatibility": parsed.compatibility,
        "allowed_tools": parsed.allowed_tools,
        "metadata": parsed.metadata,
        "files": normalize_skill_files(files),
        "updated_at": _now_iso(),
    }
    if existing and existing.get("created_at"):
        payload["created_at"] = existing.get("created_at")
    return _custom_skill(payload)


def build_agent_skills_update(
    user_settings: dict[str, Any] | None,
    *,
    custom: list[dict[str, Any]] | None = None,
    disabled_defaults: set[str] | None = None,
) -> dict[str, Any]:
    state = get_agent_skill_state(user_settings)
    current_custom = [
        skill
        for raw in (state.get("custom") or [])
        if (skill := _custom_skill(raw))
    ]
    default_ids = {skill["skill_id"] for skill in DEFAULT_AGENT_SKILLS}
    return {
        "agentSkills": {
            "custom": custom if custom is not None else current_custom,
            "disabledDefaults": sorted((disabled_defaults if disabled_defaults is not None else set(state.get("disabledDefaults") or [])) & default_ids),
        }
    }


def build_enabled_skills_prompt(
    user_settings: dict[str, Any] | None,
    limit: int = 20,
    *,
    mcp_tools: list[dict[str, Any]] | None = None,
) -> str:
    enabled = [skill for skill in list_agent_skills(user_settings) if skill.get("enabled")]
    if not enabled and not mcp_tools:
        return ""
    lines = [
        "Enabled CoComputer skills:",
        "Before choosing an agent or tool, scan this skill catalog and apply every matching skill's instructions.",
        "Call read_skill(skill_id) when you need the full instructions or exact custom workflow.",
        "If a catalog entry lists Resources, call read_skill_file(skill_id, path) for that file. Enabled skills are also mounted at /home/user/skills/<skill_id>/ when the sandbox is running.",
        "A skill is reusable instructions and routing guidance, not a connector by itself. Use the matching callable tools only when they are available.",
        "If no skill matches, continue with the normal routing policy.",
    ]
    for skill in enabled[:limit]:
        trigger = skill.get("trigger") or skill.get("description") or ""
        description = skill.get("description") or ""
        scope = ", ".join(skill.get("agent_scope") or [])
        resources = ", ".join((skill.get("resources") or [])[:8])
        extra = f" Resources: {resources}." if resources else ""
        lines.append(
            f"- {skill['skill_id']}: {skill['name']} ({skill['category']}): "
            f"{trigger} Description: {description} Scope: {scope}.{extra}"
        )

    if mcp_tools:
        lines.append("")
        lines.append("Available MCP tools (external connectors):")
        for tool in mcp_tools[:50]:
            name = tool.get("name", "")
            params = tool.get("parameters", "")
            lines.append(f"- {name}({params})")
        lines.append("Use MCP tools when they match the task. Request permission for risky MCP actions.")

    return "\n".join(lines)


def build_skill_prompt_for_agent(
    user_settings: dict[str, Any] | None,
    agent_name: str,
    *,
    mcp_tools: list[dict[str, Any]] | None = None,
    limit: int = 20,
) -> str:
    """Build a skill prompt filtered to only include skills relevant to the given agent.

    This reduces prompt noise by excluding skills that don't apply to a specific
    sub-agent's domain (e.g., desktop-control skills for browser_agent).

    Args:
        user_settings: User settings dict with skill enable/disable state.
        agent_name: Name of the agent (e.g., "computer_agent", "browser_agent").
        mcp_tools: Optional list of MCP tool metadata dicts.
        limit: Maximum number of skills to include.

    Returns:
        Skill prompt string, or empty string if no skills match.
    """
    all_skills = list_agent_skills(user_settings)
    enabled = [skill for skill in all_skills if skill.get("enabled")]

    # Filter skills whose agent_scope includes this agent
    scoped = []
    for skill in enabled:
        scope = skill.get("agent_scope")
        if scope is None or agent_name in scope:
            scoped.append(skill)

    if not scoped and not mcp_tools:
        return ""

    lines = [
        "Enabled CoComputer skills:",
        "Before choosing an agent or tool, scan this skill catalog and apply every matching skill's instructions.",
        "Call read_skill(skill_id) when you need the full instructions or exact custom workflow.",
        "If a catalog entry lists Resources, call read_skill_file(skill_id, path) for that file. Enabled skills are also mounted at /home/user/skills/<skill_id>/ when the sandbox is running.",
        "A skill is reusable instructions and routing guidance, not a connector by itself. Use the matching callable tools only when they are available.",
        "If no skill matches, continue with the normal routing policy.",
    ]
    for skill in scoped[:limit]:
        trigger = skill.get("trigger") or skill.get("description") or ""
        description = skill.get("description") or ""
        scope = ", ".join(skill.get("agent_scope") or [])
        resources = ", ".join((skill.get("resources") or [])[:8])
        extra = f" Resources: {resources}." if resources else ""
        lines.append(
            f"- {skill['skill_id']}: {skill['name']} ({skill['category']}): "
            f"{trigger} Description: {description} Scope: {scope}.{extra} "
            f"Instructions: {_clip_prompt_text(skill.get('instructions'))}"
        )

    if mcp_tools:
        lines.append("")
        lines.append("Available MCP tools (external connectors):")
        for tool in mcp_tools[:50]:
            name = tool.get("name", "")
            params = tool.get("parameters", "")
            lines.append(f"- {name}({params})")
        lines.append("Use MCP tools when they match the task. Request permission for risky MCP actions.")

    return "\n".join(lines)


public_skill = public_skill
skill_from_parsed = skill_from_parsed
get_agent_skill = get_agent_skill
