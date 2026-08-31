# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Nexus planner — single loop agent with AgentTool workers.

No ADK foreground sub-agent list is configured. Workers are explicit tools:
the planner calls them, results return, and control never leaves the planner
(structurally guaranteed by ADK's AgentTool).

This is the ONLY foreground agent. Every user turn goes through it — the
former "fast path" (ask/chat/search/current/clarify) and the artifact
mini-agent were removed. The planner self-triages on each turn: tools or not,
evidence or not, deliverable shape, skills.

See ``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from nexus.config import settings
from nexus.context_window import make_context_trimmer
from nexus.resilience import is_remote_deadline_error
from nexus.runtime_config import SessionRuntimeConfig
from nexus.tool_gateway import gate_tools
from nexus.tools._context import increment_worker_call_count

logger = logging.getLogger(__name__)

_WORKER_DEADLINE_SUMMARY = (
    "A model or storage request timed out. Try a narrower request or split it into steps."
)


def _worker_deadline_result(worker_name: str, detail: str = "") -> dict[str, Any]:
    evidence = [detail[:2000]] if detail.strip() else []
    return {
        "status": "error",
        "summary": _WORKER_DEADLINE_SUMMARY,
        "evidence": evidence,
        "artifacts": [],
        "remaining_work": [
            f"Retry {worker_name} with a narrower brief, or call run_command for a single shell step."
        ],
        "retryable": True,
        "error_code": "WORKER_DEADLINE",
    }


def _parse_worker_result(result: Any, worker_name: str) -> dict[str, Any]:
    """Require a stable evidence contract from AgentTool workers."""
    payload: Any = result
    if isinstance(result, str):
        text = result.strip()
        if is_remote_deadline_error(text):
            return _worker_deadline_result(worker_name, text)
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        candidate = fenced.group(1) if fenced else text
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {
                "status": "error",
                "summary": f"{worker_name} returned an untyped result.",
                "evidence": [text[:2000]] if text else [],
                "artifacts": [],
                "remaining_work": [
                    "Retry the worker and require the typed JSON result contract."
                ],
                "retryable": True,
                "error_code": "WORKER_RESULT_UNTYPED",
            }
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "summary": f"{worker_name} returned an invalid result type.",
            "evidence": [str(payload)[:2000]],
            "artifacts": [],
            "remaining_work": [
                "Retry the worker and require the typed JSON result contract."
            ],
            "retryable": True,
            "error_code": "WORKER_RESULT_INVALID",
        }

    status = str(payload.get("status") or "").strip().lower()
    if status not in {"success", "partial", "error", "blocked"}:
        status = "error"
        error_code = "WORKER_STATUS_INVALID"
    else:
        error_code = str(payload.get("error_code") or "")
    evidence = payload.get("evidence")
    evidence_items = (
        [str(item)[:2000] for item in evidence]
        if isinstance(evidence, list)
        else ([str(evidence)[:2000]] if evidence else [])
    )
    artifacts = payload.get("artifacts")
    artifact_items = artifacts if isinstance(artifacts, list) else []
    sources = payload.get("sources")
    source_items = [item for item in sources if isinstance(item, dict)] if isinstance(sources, list) else []
    remaining = payload.get("remaining_work")
    remaining_items = (
        [str(item)[:500] for item in remaining]
        if isinstance(remaining, list)
        else ([str(remaining)[:500]] if remaining else [])
    )
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        summary = (
            f"{worker_name} completed with evidence."
            if status == "success"
            else f"{worker_name} did not complete the requested work."
        )
    return {
        "status": status,
        "summary": summary[:1000],
        "evidence": evidence_items[:12],
        "artifacts": artifact_items[:20],
        "sources": source_items[:30],
        "remaining_work": remaining_items[:20],
        "retryable": bool(payload.get("retryable", status in {"partial", "error"})),
        "error_code": error_code,
    }


PLANNER_PROMPT = """You are CoComputer, an autonomous agent with a real Linux desktop, terminal, browser, and connectors. You own every user turn end-to-end. You run one loop: think → act with ONE tool → observe → re-plan → finish.

You never hand off control. Workers (terminal_worker, desktop_worker) and subagents are function calls that return results to you.

# Self-triage — silently decide these four before touching any tool

1. TOOLS OR NOT.
   - Answer directly, no tools, when: small talk (hi/thanks), definitions, general knowledge you already know, opinions, brainstorming, drafting from pasted text, translation of pasted text, restating or reformatting what the user already gave you, meta questions about your own capabilities.
   - Use tools when: any current fact (score, price, news, weather, release, status), any date-sensitive claim, any URL the user gave, any file/repo/desktop/connector action, any deliverable file (HTML, PDF, XLSX, DOCX), any request that says "search / look up / find / research / cite / compare / open / run / build".
   - When unsure between the two, prefer ONE cheap web_search over guessing.

2. EVIDENCE OR CONTEXT.
   - If the answer is fully in [USER MEMORY], [TURN CONTEXT], or the conversation, skip search.
   - Otherwise gather evidence: web_search / tavily_search for discovery → scrape_web_page for important pages → search_sources to pull cited chunks from material already saved under sources/. Do not stop at raw search results — synthesize with source links.
   - Research / compare / cite requests: gather at least 3 distinct sources before synthesizing.
   - For current sports / news queries, add site hints to the query when useful (site:iplt20.com, site:espncricinfo.com, site:cricbuzz.com, site:reuters.com, site:apnews.com, site:bbc.com, official league sites).

3. DELIVERABLE. Pick exactly one output shape from the user's ask and stick to it:
   - none / prose only        → reply directly, no tool.
   - markdown text            → reply directly; optional write_workspace_file for a durable note.
   - HTML                     → publish_html_artifact(title, html, filename). Or render_ui(...) when Thesys is connected (fall back to publish_html_artifact on AUTH_REQUIRED).
   - PDF                      → terminal_worker with a brief that says "call generate_pdf_report(title=..., markdown_content=..., filename=...)". Include the full markdown body in the brief. Do not draft PDF bytes or base64 inline.
   - XLSX                     → terminal_worker with a brief that says "call generate_excel_report(...)".
   - DOCX                     → terminal_worker with a brief that says "call generate_docx_report(...)".
   - PPTX                     → terminal_worker with a brief that says "call generate_pptx_report(title=..., slides=[{title, bullets}], filename=...)".
   - promote existing file    → terminal_worker with a brief that says "call save_as_artifact(path, title)".
   - code changes / repo work → terminal_worker with a scoped brief (files, commands, expected outcome).
   - GUI / browser action     → desktop_worker with a scoped brief (URL, elements, verification).
   Never describe code or a document as the answer when the user asked for a file — publish it. Never invent PDF bytes.

4. SKILLS.
   - Scan the enabled skill catalog at the top of this prompt. If any skill's trigger matches the request, call read_skill(skill_id) BEFORE using other tools, then follow the skill.
   - A slash prefix "/skill_id ..." is a hard directive: call read_skill(skill_id) first.
   - If the skill lists resources, call read_skill_file(skill_id, path) for the files you need. Enabled skills are also copied to /home/user/skills/<skill_id>/ in the sandbox.

# Tool ladder — smallest correct next action, ONE tool per step

a. read_skill                                        — matching skill first, always.
b. answer directly (no tool)                         — triage step 1 said no tools.
c. mcp__exa__web_search_exa / tavily_search / web_search — discovery of live evidence (prefer Exa MCP when connected; web_search auto-prefers Tavily when connected).
d. scrape_web_page                                   — capture important sources fully.
e. search_sources                                    — retrieve cited chunks from saved sources/.
f. publish_html_artifact / render_ui                 — HTML deliverables (no sandbox).
g. run_command(command=...)                          — ONE shell command in the sandbox. Use this for a single check (ls, pwd, models list, a test, a script). The sandbox is already the machine — do not hunt for API keys, .env files, or credentials.
h. terminal_worker(request=...)                      — batched shell, repo work, scripts, PDF/XLSX/DOCX/PPTX generation, save_as_artifact, extract_pdf_text on uploads. Prefer this when several dependent commands belong together.
i. desktop_worker(request=...)                       — GUI/browser: clicks, forms, logins, screenshots, Playwright.
j. invoke_subagent + get_subagent_result / await_subagents — independent parallel background work (research fan-out, bulk drafting).
k. request_background_task                           — user-visible long-running work needing durable resume.
l. ask_user                                          — LAST resort. One focused question. Only when a required input is genuinely missing (path, account, irreversible confirmation). Prefer options=[2-5 short choices] when the user is picking an approach; include "Something else" if they might need to type a custom answer. Omit options for values that must be typed (path, id, email). Never re-ask what the current thread already answered.
m. propose_workflow_template / update_workflow_template / publish_workflow_template — save this conversation as a reusable workflow. Propose a draft, wait for confirm/edit/dismiss. Never start a new session after proposing.

# Typed action loop and worker briefs

Before every tool call, decide: action, expected outcome, verification method, retry policy, and completion condition. Put those fields explicitly in each worker brief along with the goal, exact targets (paths, URLs, commands, data), and required evidence. Workers do NOT see this conversation.
After every result, consume its evidence, artifacts, remaining_work, and retryable fields before choosing the next action. A failed verification, unresolved tool error, missing deliverable, or remaining work forbids a completed answer.

# Workspace — sandbox-backed tasks only

- Before the first sandbox-backed worker call: prepare_task_workspace(task_summary=...), then write_todo_list([3-7 concrete steps]).
- Never call update_todo_item until write_todo_list (or prepare_task_workspace that seeds todo.md) has succeeded in this run.
- Keep todo.md current on every step: mark a step in_progress with update_todo_item(...) BEFORE starting it, then mark it done IMMEDIATELY after that step succeeds. Do not leave pending/in_progress items when you finish the turn — reconcile every item before the closing message.
- Store durable outputs in outputs/ via write_workspace_file or worker briefs.
- Never create a workspace for pure Q&A, HTML-only deliverables, or connector-only reads.

# Memory

- remember_fact(fact, category) only for lasting preferences/constraints ("always reply in Spanish", "we deploy on Cloud Run"). Saved facts return in future turns under [USER MEMORY]. Never save secrets or one-off task details.
- recall_facts is available when you need to check what has been remembered.

# Workflow templates

- When the user asks to create, save, or reuse a workflow template from this chat, call propose_workflow_template with a name, reusable instructions, and any input_fields JSON.
- After proposing, wait for the user to confirm, edit, or dismiss. Use update_workflow_template for requested changes and publish_workflow_template only after they confirm.
- Do not start a new session when creating or editing a template. Running a published template is a separate user action.

# Connectors

Prefer native connector tools over browser flows when the user has them connected: gmail_*, calendar_*, tasks_*, search_drive / read_drive_file, github_*, Exa MCP search/fetch (mcp__exa__*), tavily_search, tinyfish_web_agent, Treg MCP (mcp__treg__*) for SEO/SERP/backlinks/enrichment/ads — not for ordinary web search. If a connector returns AUTH_REQUIRED, fall back to the suggested alternative — do not clarify-loop.

# Rules

- ONE tool per step, then observe.
- On a tool error: read error_code and suggested_alternatives. Retry once with a different URL, query, or tool. Never retry the same blocked URL (HTTP_401/403/404/504 or TIMEOUT). After three failed fetches, synthesize what you have and tell the user what is still missing — do not keep scraping until the turn times out. Never clarify-loop instead of retrying.
- Sandbox timeouts are recovered automatically in this session. Retry the same worker after reconnect. If a tool returns SANDBOX_RECONNECT_FAILED, tell the user the desktop could not be restarted and to try again — do not ask them to start a new session unless reconnect already failed.
- If a tool name is rejected, re-check the tool ladder above — do not invent tool names.
- The worker call budget is enforced per turn. One shell command → run_command. Several dependent commands → ONE terminal_worker brief. Never scan the whole filesystem (find /) or dump env for secrets.
- Before invoking background work, list existing subagents and reuse recovered records; do not duplicate work after a retry or restart. Use only researcher, coder, or writer subagent types.
- If subagents were invoked, await or collect their results before final synthesis unless the user explicitly asked for background-only work.
- Never run destructive commands. Ask before irreversible actions.
- Do not ask the user to clarify what the current thread already answered — infer from context first.
- Finish only after observable evidence satisfies the completion condition. Then give a clear final message: what was done, findings, where outputs live, artifact links if published. Never end a turn on a bare tool call.
"""


class BudgetedAgentTool(AgentTool):
    """AgentTool with a per-turn invocation budget.

    The counter lives in a contextvar reset by the orchestrator at turn start,
    so the cap applies across all workers within one user turn.
    """

    async def run_async(self, *, args: dict[str, Any], tool_context) -> Any:
        count = increment_worker_call_count()
        limit = settings.max_worker_calls_per_turn
        if count > limit:
            logger.warning(
                "Worker call budget exceeded (%d/%d) — blocking %s",
                count,
                limit,
                self.name,
            )
            return {
                "status": "error",
                "summary": (
                    f"Worker call budget exceeded ({limit} per turn). Do not call workers again "
                    "this turn. Synthesize what you have, or finish with a partial result and "
                    "tell the user what remains."
                ),
                "evidence": [],
                "artifacts": [],
                "remaining_work": [
                    "Synthesize available evidence or resume in a new turn."
                ],
                "retryable": False,
                "error_code": "WORKER_BUDGET_EXCEEDED",
            }
        try:
            result = await super().run_async(args=args, tool_context=tool_context)
        except Exception as exc:
            if is_remote_deadline_error(exc):
                logger.warning(
                    "%s hit a remote deadline: %s",
                    self.name,
                    str(exc)[:300],
                )
                return _worker_deadline_result(self.name, str(exc))
            raise
        return _parse_worker_result(result, self.name)


def create_planner_agent(
    runtime_config: SessionRuntimeConfig,
    integration_tools: list | None = None,
    skill_instruction: str = "",
    model_override: str | None = None,
) -> Agent:
    """Build the planner: direct tools + budgeted AgentTool workers, no sub_agents."""
    from nexus.agents.sub_agents import create_desktop_worker, create_terminal_worker
    from nexus.model_select import create_model
    from nexus.tools.ask_user import ask_user
    from nexus.tools.bg_task import request_background_task
    from nexus.tools.docs import publish_html_artifact
    from nexus.tools.integrations import render_ui, tavily_search
    from nexus.tools.memory import recall_facts, remember_fact
    from nexus.tools.retrieval import search_sources
    from nexus.tools.skills import read_skill, read_skill_file
    from nexus.tools.templates import (
        propose_workflow_template,
        publish_workflow_template,
        update_workflow_template,
    )
    from nexus.tools.subagents import (
        await_subagents,
        cancel_subagent,
        get_subagent_result,
        invoke_subagent,
        list_subagents,
        send_message,
    )
    from nexus.tools.bash import run_command
    from nexus.tools.web import scrape_web_page, web_search
    from nexus.tools.workspace import (
        initialize_task_state,
        list_workspace_files,
        prepare_task_workspace,
        read_task_state,
        read_workspace_file,
        update_task_state,
        update_todo_item,
        write_todo_list,
        write_workspace_file,
    )

    terminal_worker = create_terminal_worker(runtime_config, skill_instruction=skill_instruction)
    desktop_worker = create_desktop_worker(runtime_config, skill_instruction=skill_instruction)

    direct_tools = [
        prepare_task_workspace,
        initialize_task_state,
        update_task_state,
        read_task_state,
        write_todo_list,
        update_todo_item,
        write_workspace_file,
        read_workspace_file,
        list_workspace_files,
        run_command,
        web_search,
        scrape_web_page,
        tavily_search,
        search_sources,
        publish_html_artifact,
        render_ui,
        read_skill,
        read_skill_file,
        remember_fact,
        recall_facts,
        ask_user,
        request_background_task,
        propose_workflow_template,
        update_workflow_template,
        publish_workflow_template,
        invoke_subagent,
        send_message,
        get_subagent_result,
        list_subagents,
        cancel_subagent,
        await_subagents,
        *(integration_tools or []),
    ]
    workflow_instruction = ""
    if settings.deep_research_workflow_enabled:
        from nexus.deep_research_workflow import (
            create_deep_research_workflow_tool,
        )

        direct_tools.append(create_deep_research_workflow_tool())
        workflow_instruction = """

# Deterministic deep-research workflow pilot
- deep_research_workflow(request=...) is available only for explicit multi-source research/report requests.
- Prepare the task workspace first. Use the workflow once, consume its reviewed evidence and artifacts, then perform final semantic synthesis yourself.
- Never use it for normal chat, one-page lookup, browser clicking, forms, or GUI work. Those remain on the normal typed planner/controller loop.
"""

    worker_tools = [
        BudgetedAgentTool(agent=terminal_worker, skip_summarization=True),
        BudgetedAgentTool(agent=desktop_worker, skip_summarization=True),
    ]

    instruction = (
        PLANNER_PROMPT
        if not skill_instruction
        else f"{PLANNER_PROMPT}\n\n{skill_instruction}"
    )
    instruction += workflow_instruction

    return Agent(
        name="nexus_planner",
        model=create_model(
            "planner",
            runtime_config,
            model_override=model_override,
        ),
        instruction=instruction,
        tools=[*gate_tools(direct_tools), *worker_tools],
        before_model_callback=make_context_trimmer(runtime_config),
    )


__all__ = [
    "PLANNER_PROMPT",
    "BudgetedAgentTool",
    "create_planner_agent",
]
