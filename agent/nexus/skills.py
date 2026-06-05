# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

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
        "agent_scope": ["browser_agent", "research_browser_agent", "deepresearcher", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "web-automation",
        "name": "Web Automation",
        "category": "Browser",
        "description": "Navigate sites, forms, and browser workflows.",
        "trigger": "Use when the task requires web pages, forms, logins, or browser-only UI.",
        "instructions": "Use browser tools for navigation and keep user credentials scoped.",
        "agent_scope": ["browser_agent", "research_browser_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "codebase-engineering",
        "name": "Codebase Engineering",
        "category": "Coding",
        "description": "Inspect repos, edit files, run tests, and fix bugs.",
        "trigger": "Use for code changes, debugging, refactors, tests, and repo analysis.",
        "instructions": "Read the code first, keep edits scoped, and verify with relevant commands.",
        "agent_scope": ["code_agent", "research_code_agent", "deepresearcher", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "terminal-ops",
        "name": "Terminal Operations",
        "category": "System",
        "description": "Run shell commands, scripts, package tools, and process checks.",
        "trigger": "Use for CLI tasks, environment checks, logs, installs, and command output.",
        "instructions": "Prefer precise commands, avoid destructive actions, and report key output.",
        "agent_scope": ["code_agent", "research_code_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "desktop-control",
        "name": "Desktop Control",
        "category": "Computer",
        "description": "Interact with GUI apps, screenshots, menus, and dialogs.",
        "trigger": "Use for visible desktop state, native apps, file pickers, and mouse/keyboard work.",
        "instructions": "Use computer control only when visual GUI interaction is required.",
        "agent_scope": ["computer_agent", "research_computer_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "workspace-files",
        "name": "Workspace Files",
        "category": "Files",
        "description": "Create, read, and organize workspace artifacts.",
        "trigger": "Use when the task needs files, reports, exports, or saved artifacts.",
        "instructions": "Create durable files in the session workspace and name outputs clearly.",
        "agent_scope": ["code_agent", "browser_agent", "computer_agent", "deepresearcher", "research_code_agent", "research_browser_agent", "research_computer_agent", "research_reviewer_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "data-analysis",
        "name": "Data Analysis",
        "category": "Analysis",
        "description": "Analyze CSV, JSON, logs, metrics, and structured data.",
        "trigger": "Use for calculations, comparisons, charts, metrics, and dataset summaries.",
        "instructions": "Use structured parsing where possible and explain assumptions.",
        "agent_scope": ["code_agent", "deepresearcher", "research_code_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "spreadsheet-work",
        "name": "Spreadsheet Work",
        "category": "Documents",
        "description": "Create and edit spreadsheets, formulas, tables, and charts.",
        "trigger": "Use for XLSX/CSV work, financial tables, formulas, and spreadsheet exports.",
        "instructions": "Preserve formulas and formatting, and validate generated sheets.",
        "agent_scope": ["code_agent", "computer_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "document-work",
        "name": "Document Work",
        "category": "Documents",
        "description": "Draft, edit, summarize, and format documents.",
        "trigger": "Use for DOCX, Markdown, reports, summaries, and written deliverables.",
        "instructions": "Produce concise, well-structured documents with clear filenames.",
        "agent_scope": ["code_agent", "deepresearcher", "research_code_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "presentation-work",
        "name": "Presentation Work",
        "category": "Documents",
        "description": "Create slide decks, outlines, and presentation content.",
        "trigger": "Use for PPTX, slide plans, pitch decks, and visual summaries.",
        "instructions": "Keep slides scannable and organize content into strong sections.",
        "agent_scope": ["code_agent", "computer_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "github-review",
        "name": "GitHub Review",
        "category": "Developer",
        "description": "Review PRs, issues, diffs, and repository changes.",
        "trigger": "Use for GitHub issues, pull requests, code review, and CI context.",
        "instructions": "Prioritize correctness, security, regressions, and test gaps.",
        "agent_scope": ["code_agent", "deepresearcher", "research_code_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "qa-testing",
        "name": "QA Testing",
        "category": "Testing",
        "description": "Run checks, inspect failures, and verify app behavior.",
        "trigger": "Use for test plans, smoke tests, failing tests, and validation.",
        "instructions": "Prefer targeted verification first, then broader checks when risk is high.",
        "agent_scope": ["code_agent", "computer_agent", "research_code_agent", "research_computer_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "mcp-tool-use",
        "name": "MCP Tool Use",
        "category": "Tools",
        "description": "Use enabled MCP connectors and remote tool servers.",
        "trigger": "Use when external MCP tools are selected or clearly useful.",
        "instructions": "Choose the smallest useful external tool and request permission for risky actions.",
        "agent_scope": ["browser_agent", "code_agent", "computer_agent", "deepresearcher", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "email-calendar",
        "name": "Email and Calendar",
        "category": "Productivity",
        "description": "Work with Gmail, Calendar, Tasks, and Drive when connected.",
        "trigger": "Use for email search/send, calendar events, tasks, and Drive files.",
        "instructions": "Confirm recipients, dates, and irreversible sends before acting.",
        "agent_scope": ["browser_agent", "code_agent", "nexus_orchestrator", "nexus"],
    },
    {
        "skill_id": "workflow-templates",
        "name": "Workflow Templates",
        "category": "Automation",
        "description": "Reuse saved task workflows and repeatable operating procedures.",
        "trigger": "Use when a task matches a saved workflow or should become repeatable.",
        "instructions": "Follow the saved process and adapt only the user-provided inputs.",
        "agent_scope": ["nexus_orchestrator", "nexus"],
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
        "Before choosing an agent or tool, scan these skills and apply every skill whose trigger matches the user's request.",
        "A skill is reusable instructions and routing guidance, not a connector by itself. Use the matching callable tools only when they are available.",
        "If no skill matches, continue with the normal routing policy.",
    ]
    for skill in enabled[:limit]:
        trigger = skill.get("trigger") or skill.get("description") or ""
        lines.append(f"- {skill['name']} ({skill['category']}): {trigger} Instructions: {skill['instructions']}")

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
        "Before choosing an agent or tool, scan these skills and apply every skill whose trigger matches the user's request.",
        "A skill is reusable instructions and routing guidance, not a connector by itself. Use the matching callable tools only when they are available.",
        "If no skill matches, continue with the normal routing policy.",
    ]
    for skill in scoped[:limit]:
        trigger = skill.get("trigger") or skill.get("description") or ""
        lines.append(f"- {skill['name']} ({skill['category']}): {trigger} Instructions: {skill['instructions']}")

    if mcp_tools:
        lines.append("")
        lines.append("Available MCP tools (external connectors):")
        for tool in mcp_tools[:50]:
            name = tool.get("name", "")
            params = tool.get("parameters", "")
            lines.append(f"- {name}({params})")
        lines.append("Use MCP tools when they match the task. Request permission for risky MCP actions.")

    return "\n".join(lines)
