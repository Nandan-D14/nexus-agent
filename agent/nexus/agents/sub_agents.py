# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""AgentTool workers for the single planner: terminal and desktop."""

from __future__ import annotations

from google.adk.agents import Agent

from nexus.runtime_config import SessionRuntimeConfig
from nexus.context_condenser import make_context_callbacks
from nexus.tool_gateway import gate_tools
from nexus.tools.computer import (
    move_mouse,
    left_click,
    right_click,
    double_click,
    triple_click,
    type_text,
    press_key,
    scroll_screen,
    drag,
)
from nexus.tools.screen import take_screenshot
from nexus.tools.bash import run_command
from nexus.tools.browser import open_browser
from nexus.tools.browser_playwright import (
    playwright_navigate,
    playwright_click,
    playwright_type,
    playwright_get_text,
    playwright_wait_for,
    playwright_snapshot,
    playwright_verify,
)
from nexus.tools.workspace import (
    write_workspace_file,
    read_workspace_file,
    list_workspace_files,
)
from nexus.tools.docs import (
    extract_document_text,
    extract_pdf_text,
    generate_docx_report,
    generate_excel_report,
    generate_pdf_report,
    generate_pptx_report,
    publish_app_preview,
    save_as_artifact,
)
from nexus.tools.skills import read_skill, read_skill_file

# ---------------------------------------------------------------------------
# Worker system prompts
# ---------------------------------------------------------------------------

TERMINAL_WORKER_PROMPT = """You are terminal_worker, a focused CoComputer worker for shell and file work.
You receive one scoped task brief from the planner, do the work, and return a concise result.
You never talk to the user directly.

Do:
- shell commands, repo/file/log/config inspection, installs, scripts, process checks
- file creation and edits in the workspace, data exports
- reading uploaded PDFs with extract_pdf_text (never cat PDFs or base64 dumps)
- generating documents with generate_pdf_report, generate_excel_report, generate_docx_report, or generate_pptx_report, and promoting files with save_as_artifact
- For slides, call generate_pptx_report with layouted slides (title, section, content, split, stats, quote, closing). Do not write python-pptx or LibreOffice macros.
- publishing a live app preview with publish_app_preview after a Vite/Next/Flask (or similar) server is bound to 0.0.0.0 in the current workspace. Vite needs server.allowedHosts: true or the Preview iframe is blank.

Workflow:
1. Read the brief. If a workspace file list or task state is referenced, read it first.
2. Work with commands and file tools. Prefer pwd, workspace ls, and scoped find/cat/grep/ps over guessing. Never run find / or scan the whole filesystem. Never hunt for API keys, .env files, or dump env — the sandbox is already authenticated.
3. Chain dependent commands with &&. Use background=True for processes that keep running.
4. Write durable outputs into outputs/ with write_workspace_file(...).
5. Verify commands, tests, or artifact paths before finishing.
6. Return ONLY one JSON object with this contract:
   {"status":"success|partial|error|blocked","summary":"short factual result","evidence":["exit codes, test results, or file checks"],"artifacts":[{"path":"...","kind":"..."}],"remaining_work":[],"retryable":false,"error_code":""}
   Use status=success only when the requested state is verified. Put unfinished steps in remaining_work. On timeout or tool failure still return this JSON (status=error, error_code set) — never prose.

Rules:
- Requested actions are authorized; tool policy and approvals gate risk at runtime. If an action is denied, or needs a user decision you cannot get, return status=blocked with the reason — never ask questions.
- On a tool error, read the message and suggested_alternatives, fix your arguments, and retry — at most 2 retries per failing action. Then return status=error with what you tried.
- If a tool says the sandbox is restarting, or returns SANDBOX_RECONNECT_FAILED, retry the same command. Do not return status=blocked with invented codes such as SANDBOX_NOT_RUNNING. Do not tell the planner to start a new session — recovery stays in this session.
- If the task needs GUI interaction or a browser, say so in your summary instead of improvising.
- Keep output small: exact paths, exit codes, short excerpts — not full logs."""

DESKTOP_WORKER_PROMPT = """You are desktop_worker, a focused CoComputer worker for GUI, browser, and visual tasks.
You receive one scoped task brief from the planner, do the work, and return a concise result.
You never talk to the user directly.

SCREEN: 1324x968 pixels. (0,0) = top-left. Taskbar at bottom (~y=940).

Do:
- native desktop apps, dialogs, menus, file pickers, drag/drop
- website interaction: forms, logins, downloads, dynamic pages
- visual verification of on-screen state

Workflow:
1. Read the brief. Open the target app or site (open_browser for web).
2. Prefer Playwright tools (playwright_navigate/click/type/get_text/wait_for/snapshot/verify) for web DOM work;
   fall back to coordinates only when DOM access fails.
3. take_screenshot() only when you need visual state to decide the next action.
4. After any click/type/scroll/drag, the previous screenshot is stale — let the screen settle.
5. Act on what you observe. Do not describe the screen without acting.
6. Verify the final DOM or screen state after the last mutation.
7. Return ONLY one JSON object with this contract:
   {"status":"success|partial|error|blocked","summary":"short factual result","evidence":["observed DOM or screen state"],"artifacts":[],"remaining_work":[],"retryable":false,"error_code":""}
   Use status=success only after a fresh Playwright verification or screenshot confirms the expected state. Put unfinished steps in remaining_work.

Rules:
- No shell commands — that is terminal_worker's job; say so in your summary if needed.
- Requested actions are authorized; tool policy and approvals gate risk at runtime. If an action is denied, or needs a user decision you cannot get (login, CAPTCHA, choice), return status=blocked with the reason — never ask questions.
- On a tool error, read the message and suggested_alternatives, adjust, and retry — at most 2 retries per failing action. Then return status=error with what you tried.
- If coordinates seem off, adjust and retry instead of re-screenshotting repeatedly."""


# ---------------------------------------------------------------------------
# Worker factories
# ---------------------------------------------------------------------------

def worker_skill_index(skill_instruction: str = "") -> str:
    """Minimal-mode skills section for workers.

    Workers get only the skill ids/names (load one with read_skill when the
    brief needs it). Planner-only content — agent routing guidance and the
    MCP connector list, which workers cannot call — is dropped.
    """
    entries: list[str] = []
    for line in str(skill_instruction or "").splitlines():
        if line.startswith("Available MCP tools"):
            break
        if line.startswith("- "):
            head = line[2:].split(" Description:", 1)[0].strip()
            entries.append(f"- {head[:200]}")
    if not entries:
        return ""
    return "Skills (call read_skill(skill_id) only if the brief needs one):\n" + "\n".join(entries)


def _with_skill_instruction(instruction: str, skill_instruction: str = "") -> str:
    skills = worker_skill_index(skill_instruction)
    if not skills:
        return instruction
    return f"{instruction}\n\n{skills}"


def create_terminal_worker(
    runtime_config: SessionRuntimeConfig,
    skill_instruction: str = "",
) -> Agent:
    """Terminal worker — shell, file, and document surface (14 tools)."""
    from nexus.model_select import create_model

    return Agent(
        name="terminal_worker",
        description=(
            "Runs shell commands and file-system work in the sandbox: repo/file/log "
            "inspection, installs, scripts, file creation, PDF/report generation. "
            "No GUI, no browser."
        ),
        model=create_model("worker", runtime_config),
        instruction=_with_skill_instruction(TERMINAL_WORKER_PROMPT, skill_instruction),
        tools=gate_tools([
            run_command,
            write_workspace_file,
            read_workspace_file,
            list_workspace_files,
            extract_pdf_text,
            extract_document_text,
            generate_pdf_report,
            generate_excel_report,
            generate_docx_report,
            generate_pptx_report,
            save_as_artifact,
            publish_app_preview,
            read_skill,
            read_skill_file,
        ]),
        before_model_callback=make_context_callbacks(runtime_config),
    )


def create_desktop_worker(
    runtime_config: SessionRuntimeConfig,
    skill_instruction: str = "",
) -> Agent:
    """Desktop worker — GUI, browser, and visual surface (20 tools)."""
    from nexus.model_select import create_model

    return Agent(
        name="desktop_worker",
        description=(
            "Controls the desktop and browser visually: opens sites and apps, clicks, "
            "types, fills forms, verifies on-screen state, Playwright DOM automation. "
            "No shell commands."
        ),
        model=create_model("worker_visual", runtime_config),
        instruction=_with_skill_instruction(DESKTOP_WORKER_PROMPT, skill_instruction),
        tools=gate_tools([
            take_screenshot,
            move_mouse,
            left_click,
            right_click,
            double_click,
            triple_click,
            type_text,
            press_key,
            scroll_screen,
            drag,
            open_browser,
            playwright_navigate,
            playwright_click,
            playwright_type,
            playwright_get_text,
            playwright_wait_for,
            playwright_snapshot,
            playwright_verify,
            read_skill,
            read_skill_file,
        ]),
        before_model_callback=make_context_callbacks(runtime_config),
    )


# ---------------------------------------------------------------------------
# Removed legacy transfer-mesh factories (kept as explicit errors so stale
# callers fail loudly with the replacement instead of an ImportError).
# ---------------------------------------------------------------------------

def create_computer_agent(
    runtime_config: SessionRuntimeConfig,
    skill_instruction: str = "",
) -> Agent:
    """Removed; use :func:`create_desktop_worker` via the single planner path."""
    raise RuntimeError(
        "create_computer_agent was removed; use create_desktop_worker through "
        "create_planner_agent"
    )


def create_browser_agent(
    runtime_config: SessionRuntimeConfig,
    skill_instruction: str = "",
) -> Agent:
    """Removed; use :func:`create_desktop_worker` via the single planner path."""
    raise RuntimeError(
        "create_browser_agent was removed; use create_desktop_worker through "
        "create_planner_agent"
    )


def create_code_agent(
    runtime_config: SessionRuntimeConfig,
    skill_instruction: str = "",
) -> Agent:
    """Removed; use :func:`create_terminal_worker` via the single planner path."""
    raise RuntimeError(
        "create_code_agent was removed; use create_terminal_worker through "
        "create_planner_agent"
    )


def create_deepresearcher_agent(
    runtime_config: SessionRuntimeConfig,
    extra_tools: list | None = None,
    skill_instruction: str = "",
) -> Agent:
    """Removed; deep research uses the planner plus researcher subagents."""
    raise RuntimeError(
        "create_deepresearcher_agent was removed; use create_planner_agent with "
        "researcher subagents or deep_research_workflow"
    )
