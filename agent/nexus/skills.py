"""Agent skill registry and prompt helpers."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any


DEFAULT_AGENT_SKILLS: list[dict[str, Any]] = [
    {
        "skill_id": "browser-research",
        "name": "Browser Research",
        "category": "Research",
        "description": "Search the web, read sources, and collect citations.",
        "trigger": "Use for web research, current facts, docs, and source-backed answers.",
        "instructions": "Gather evidence from reliable sources and summarize with source links.",
    },
    {
        "skill_id": "web-automation",
        "name": "Web Automation",
        "category": "Browser",
        "description": "Navigate sites, forms, and browser workflows.",
        "trigger": "Use when the task requires web pages, forms, logins, or browser-only UI.",
        "instructions": "Use browser tools for navigation and keep user credentials scoped.",
    },
    {
        "skill_id": "codebase-engineering",
        "name": "Codebase Engineering",
        "category": "Coding",
        "description": "Inspect repos, edit files, run tests, and fix bugs.",
        "trigger": "Use for code changes, debugging, refactors, tests, and repo analysis.",
        "instructions": "Read the code first, keep edits scoped, and verify with relevant commands.",
    },
    {
        "skill_id": "terminal-ops",
        "name": "Terminal Operations",
        "category": "System",
        "description": "Run shell commands, scripts, package tools, and process checks.",
        "trigger": "Use for CLI tasks, environment checks, logs, installs, and command output.",
        "instructions": "Prefer precise commands, avoid destructive actions, and report key output.",
    },
    {
        "skill_id": "desktop-control",
        "name": "Desktop Control",
        "category": "Computer",
        "description": "Interact with GUI apps, screenshots, menus, and dialogs.",
        "trigger": "Use for visible desktop state, native apps, file pickers, and mouse/keyboard work.",
        "instructions": "Use computer control only when visual GUI interaction is required.",
    },
    {
        "skill_id": "workspace-files",
        "name": "Workspace Files",
        "category": "Files",
        "description": "Create, read, and organize workspace artifacts.",
        "trigger": "Use when the task needs files, reports, exports, or saved artifacts.",
        "instructions": "Create durable files in the session workspace and name outputs clearly.",
    },
    {
        "skill_id": "data-analysis",
        "name": "Data Analysis",
        "category": "Analysis",
        "description": "Analyze CSV, JSON, logs, metrics, and structured data.",
        "trigger": "Use for calculations, comparisons, charts, metrics, and dataset summaries.",
        "instructions": "Use structured parsing where possible and explain assumptions.",
    },
    {
        "skill_id": "spreadsheet-work",
        "name": "Spreadsheet Work",
        "category": "Documents",
        "description": "Create and edit spreadsheets, formulas, tables, and charts.",
        "trigger": "Use for XLSX/CSV work, financial tables, formulas, and spreadsheet exports.",
        "instructions": "Preserve formulas and formatting, and validate generated sheets.",
    },
    {
        "skill_id": "document-work",
        "name": "Document Work",
        "category": "Documents",
        "description": "Draft, edit, summarize, and format documents.",
        "trigger": "Use for DOCX, Markdown, reports, summaries, and written deliverables.",
        "instructions": "Produce concise, well-structured documents with clear filenames.",
    },
    {
        "skill_id": "presentation-work",
        "name": "Presentation Work",
        "category": "Documents",
        "description": "Create slide decks, outlines, and presentation content.",
        "trigger": "Use for PPTX, slide plans, pitch decks, and visual summaries.",
        "instructions": "Keep slides scannable and organize content into strong sections.",
    },
    {
        "skill_id": "github-review",
        "name": "GitHub Review",
        "category": "Developer",
        "description": "Review PRs, issues, diffs, and repository changes.",
        "trigger": "Use for GitHub issues, pull requests, code review, and CI context.",
        "instructions": "Prioritize correctness, security, regressions, and test gaps.",
    },
    {
        "skill_id": "qa-testing",
        "name": "QA Testing",
        "category": "Testing",
        "description": "Run checks, inspect failures, and verify app behavior.",
        "trigger": "Use for test plans, smoke tests, failing tests, and validation.",
        "instructions": "Prefer targeted verification first, then broader checks when risk is high.",
    },
    {
        "skill_id": "mcp-tool-use",
        "name": "MCP Tool Use",
        "category": "Tools",
        "description": "Use enabled MCP connectors and remote tool servers.",
        "trigger": "Use when external MCP tools are selected or clearly useful.",
        "instructions": "Choose the smallest useful external tool and request permission for risky actions.",
    },
    {
        "skill_id": "email-calendar",
        "name": "Email and Calendar",
        "category": "Productivity",
        "description": "Work with Gmail, Calendar, Tasks, and Drive when connected.",
        "trigger": "Use for email search/send, calendar events, tasks, and Drive files.",
        "instructions": "Confirm recipients, dates, and irreversible sends before acting.",
    },
    {
        "skill_id": "workflow-templates",
        "name": "Workflow Templates",
        "category": "Automation",
        "description": "Reuse saved task workflows and repeatable operating procedures.",
        "trigger": "Use when a task matches a saved workflow or should become repeatable.",
        "instructions": "Follow the saved process and adapt only the user-provided inputs.",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, fallback: str = "skill") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:60] or fallback


def _default_skill(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        **raw,
        "source": "built_in",
        "enabled": True,
        "created_at": None,
        "updated_at": None,
    }


def _custom_skill(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    instructions = str(raw.get("instructions") or "").strip()
    if not name or not instructions:
        return None
    skill_id = str(raw.get("skill_id") or raw.get("id") or "").strip()
    if not skill_id:
        skill_id = f"user-{_slug(name)}-{uuid.uuid4().hex[:6]}"
    return {
        "skill_id": skill_id[:96],
        "name": name[:80],
        "category": str(raw.get("category") or "Custom").strip()[:40] or "Custom",
        "description": str(raw.get("description") or "").strip()[:240],
        "trigger": str(raw.get("trigger") or "").strip()[:500],
        "instructions": instructions[:4000],
        "source": "user",
        "enabled": bool(raw.get("enabled", True)),
        "created_at": raw.get("created_at") or _now_iso(),
        "updated_at": raw.get("updated_at") or _now_iso(),
    }


def get_agent_skill_state(user_settings: dict[str, Any] | None) -> dict[str, Any]:
    state = (user_settings or {}).get("agentSkills")
    return state if isinstance(state, dict) else {}


def list_agent_skills(user_settings: dict[str, Any] | None) -> list[dict[str, Any]]:
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
    return [*defaults, *custom]


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


def build_enabled_skills_prompt(user_settings: dict[str, Any] | None, limit: int = 20) -> str:
    enabled = [skill for skill in list_agent_skills(user_settings) if skill.get("enabled")]
    if not enabled:
        return ""
    lines = [
        "Enabled CoComputer skills:",
        "Before choosing an agent or tool, scan these skills and apply every skill whose trigger matches the user's request.",
        "A skill is reusable instructions and routing guidance, not a connector by itself. Use the matching callable tools only when they are available.",
        "If no skill matches, continue with the normal routing policy.",
    ]
    for skill in enabled[:limit]:
        trigger = skill.get("trigger") or skill.get("description") or ""
        lines.append(f"- {skill['name']} ({skill['category']}): {trigger} Instructions: {skill['instructions']}")
    return "\n".join(lines)
