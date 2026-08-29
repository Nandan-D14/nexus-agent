# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Context-window budgeting for LLM turns.

The ADK Runner re-sends the full session history every turn. Without a cap the
prompt grows past the model's context limit (e.g. Kimi-K2.6 = 262144 tokens),
raising ``BadRequestError: input exceeds the model context limit``.

``make_context_trimmer`` returns an ADK ``before_model_callback`` that trims the
oldest ``llm_request.contents`` so the per-turn prompt stays under a budget
derived from the model limit, always preserving the system instruction and the
most recent turns. Trimming is char/4 estimated (deterministic, no extra deps)
with a safety margin, and it avoids orphaning tool responses.
"""

from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from nexus.config import settings

logger = logging.getLogger(__name__)

# #region agent log
def _dbg(hid: str, loc: str, msg: str, data: dict | None = None) -> None:
    import json, time, urllib.request
    payload = {"sessionId": "19cd7e", "hypothesisId": hid, "location": loc, "message": msg, "data": data or {}, "timestamp": int(time.time() * 1000), "runId": "post-fix"}
    try:
        with open(r"c:\Users\nanda\OneDrive\Desktop\co-computer\debug-19cd7e.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:7421/ingest/08b059be-2c03-45ae-97a1-bb3c6f862ec1",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Debug-Session-Id": "19cd7e"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=0.3).read()
    except Exception:
        pass
# #endregion

_TRIM_NOTE = (
    "[earlier turns trimmed to fit the model context window; full history is "
    "preserved in the durable session store]"
)
# Rough chars-per-token; conservative so we under-estimate the budget usage.
_CHARS_PER_TOKEN = 4
# Per-message structural overhead (role markers, delimiters).
_MESSAGE_OVERHEAD_TOKENS = 8


def _estimate_tokens_from_text(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _estimate_tokens_for_content(content) -> int:
    chars = 0
    for part in getattr(content, "parts", None) or []:
        text = getattr(part, "text", None)
        if text:
            chars += len(text)
        fc = getattr(part, "function_call", None)
        if fc is not None:
            chars += len(str(getattr(fc, "args", "") or ""))
            chars += len(getattr(fc, "name", "") or "")
        fr = getattr(part, "function_response", None)
        if fr is not None:
            chars += len(str(getattr(fr, "response", "") or ""))
    return chars // _CHARS_PER_TOKEN + _MESSAGE_OVERHEAD_TOKENS


def _estimate_system_tokens(llm_request) -> int:
    config = getattr(llm_request, "config", None)
    system = getattr(config, "system_instruction", None) if config else None
    if not system:
        return 0
    if isinstance(system, str):
        return _estimate_tokens_from_text(system)
    # types.Content or list of Content/parts — fall back to a string estimate.
    return _estimate_tokens_from_text(str(system))


def _has_function_response(content) -> bool:
    return any(
        getattr(part, "function_response", None) is not None
        for part in (getattr(content, "parts", None) or [])
    )


def _has_function_call(content) -> bool:
    return any(
        getattr(part, "function_call", None) is not None
        for part in (getattr(content, "parts", None) or [])
    )


def _drop_leading_orphan_tool_results(kept: list) -> list:
    """Drop leading tool-response turns whose matching call was trimmed.

    A ``function_response`` with no preceding ``function_call`` in-context makes
    the model API reject the request, so strip any such orphans at the front.
    """
    index = 0
    while index < len(kept) - 1 and _has_function_response(kept[index]):
        index += 1
    return kept[index:]


def _drop_trailing_orphan_tool_calls(kept: list) -> list:
    """Drop trailing ``function_call`` turns that have no following response.

    A turn-cap break can leave a bare ``function_call`` at the tail with no
    matching ``function_response``; the next API call rejects that. Strip such
    trailing orphans so the resend stays valid.
    """
    while (
        len(kept) > 1
        and _has_function_call(kept[-1])
        and not _has_function_response(kept[-1])
    ):
        kept = kept[:-1]
    return kept


# Groq on-demand TPM for small SKUs is ~8k; stay under that including tokenizer slack.
_GROQ_INPUT_TOKEN_CAP = 5500
_NEVER_DROP_TOOLS = frozenset({
    "terminal_worker",
    "desktop_worker",
    "run_command",
    "prepare_task_workspace",
    "write_workspace_file",
    "generate_excel_report",
    "generate_pptx_report",
})
_CORE_TOOL_NAMES = _NEVER_DROP_TOOLS | frozenset({
    "initialize_task_state",
    "update_task_state",
    "read_task_state",
    "write_todo_list",
    "update_todo_item",
    "read_workspace_file",
    "list_workspace_files",
    "web_search",
    "scrape_web_page",
    "publish_html_artifact",
    "ask_user",
    "generate_pdf_report",
    "generate_docx_report",
    "save_as_artifact",
    "extract_pdf_text",
    "take_screenshot",
})


def _is_groq_runtime(runtime_config: Any | None) -> bool:
    if runtime_config is None:
        return False
    provider = str(getattr(runtime_config, "llm_provider", "") or "").lower()
    base = str(getattr(runtime_config, "llm_api_base", "") or "").lower()
    return provider == "groq" or "api.groq.com" in base


def _input_token_budget(runtime_config: Any | None) -> tuple[int, int]:
    limit = max(1000, int(settings.model_context_limit))
    budget = int(limit * float(settings.context_input_budget_ratio))
    if _is_groq_runtime(runtime_config):
        budget = min(budget, _GROQ_INPUT_TOKEN_CAP)
    return limit, budget


def _iter_function_decls(tools: list | None):
    for tool_index, tool in enumerate(tools or []):
        decls = list(getattr(tool, "function_declarations", None) or [])
        for decl_index, decl in enumerate(decls):
            yield tool_index, decl_index, tool, decl


def _estimate_tokens_for_tools(tools: list | None) -> int:
    chars = 0
    for _ti, _di, tool, decl in _iter_function_decls(tools):
        chars += len(str(getattr(decl, "name", "") or ""))
        chars += len(str(getattr(decl, "description", "") or ""))
        params = getattr(decl, "parameters", None)
        if params is None:
            params = getattr(decl, "parameters_json_schema", None)
        if params is not None:
            chars += len(str(params))
        chars += 24
    if tools and chars == 0:
        chars = len(str(tools))
    return chars // _CHARS_PER_TOKEN


def _decl_drop_rank(name: str) -> int:
    key = (name or "").strip()
    if key in _NEVER_DROP_TOOLS:
        return 1000
    if key in _CORE_TOOL_NAMES:
        return 100
    lowered = key.lower()
    if lowered.startswith("mcp") or "__" in lowered:
        return 0
    return 10


def _prune_tools_to_budget(tools: list, budget: int) -> tuple[list, list[str]]:
    """Drop lowest-priority function declarations until tool schemas fit ``budget``."""
    current = list(tools)
    dropped: list[str] = []
    while current and _estimate_tokens_for_tools(current) > budget:
        best: tuple[int, int, int, int, str] | None = None
        for tool_index, decl_index, _tool, decl in _iter_function_decls(current):
            name = str(getattr(decl, "name", "") or "")
            rank = _decl_drop_rank(name)
            if rank >= 1000:
                continue
            size = len(str(decl))
            key = (rank, -size, tool_index, decl_index, name)
            if best is None or key[:4] < best[:4]:
                best = key
        if best is None:
            break
        tool_index, decl_index, name = best[2], best[3], best[4]
        decls = list(getattr(current[tool_index], "function_declarations", None) or [])
        if not (0 <= decl_index < len(decls)):
            break
        decls.pop(decl_index)
        dropped.append(name or f"tool_{tool_index}")
        if decls:
            current[tool_index].function_declarations = decls
        else:
            current.pop(tool_index)
    return current, dropped


def make_context_trimmer(runtime_config: Any | None = None):
    """Return a before_model_callback that budgets the prompt to the context window."""

    def before_model_callback(callback_context, llm_request):
        contents = list(getattr(llm_request, "contents", None) or [])
        sys_tok = _estimate_system_tokens(llm_request)
        content_tok = sum(_estimate_tokens_for_content(c) for c in contents)
        limit, budget = _input_token_budget(runtime_config)
        cfg = getattr(llm_request, "config", None)
        tools = getattr(cfg, "tools", None) if cfg else None
        tool_list = list(tools) if isinstance(tools, list) else []
        tool_tok = _estimate_tokens_for_tools(tool_list)
        groq = _is_groq_runtime(runtime_config)
        skip_history = (not settings.enforce_context_budget) or (
            len(contents) <= 1 and not groq and (sys_tok + content_tok + tool_tok) <= budget
        )
        # #region agent log
        _dbg("A", "context_window.py:before_model", "trimmer_budget", {
            "n_contents": len(contents),
            "sys_tok": sys_tok,
            "content_tok": content_tok,
            "tool_tok": tool_tok,
            "sum_tok": sys_tok + content_tok + tool_tok,
            "limit": limit,
            "budget": budget,
            "tool_n": len(tool_list),
            "groq": groq,
            "enforce": bool(settings.enforce_context_budget),
            "skip_short": skip_history,
        })
        # #endregion
        if not settings.enforce_context_budget:
            return None

        dropped_tools: list[str] = []
        if cfg is not None and tool_list:
            tool_budget = max(800, budget - sys_tok - content_tok)
            pruned, dropped_tools = _prune_tools_to_budget(tool_list, tool_budget)
            if dropped_tools:
                cfg.tools = pruned
                logger.info(
                    "Pruned %d tool schemas to fit token budget (~%d remaining tools)",
                    len(dropped_tools),
                    len(pruned),
                )
                # #region agent log
                _dbg("A", "context_window.py:before_model", "tools_pruned", {
                    "dropped_n": len(dropped_tools),
                    "dropped": dropped_tools[:20],
                    "kept_n": len(pruned),
                    "tool_budget": tool_budget,
                })
                # #endregion

        if len(contents) <= 1:
            return None
        available = budget - _estimate_system_tokens(llm_request) - _estimate_tokens_for_tools(
            getattr(cfg, "tools", None) if cfg else None
        )
        if available <= 0:
            available = budget

        kept: list = []
        total = 0
        for content in reversed(contents):
            tokens = _estimate_tokens_for_content(content)
            if kept and total + tokens > available:
                break
            kept.append(content)
            total += tokens
        kept.reverse()
        if not kept:
            kept = [contents[-1]]
        kept = _drop_leading_orphan_tool_results(kept)
        # Repair a bare trailing function_call (e.g. left by a turn-cap break)
        # that has no matching function_response, which would 400 the resend.
        kept = _drop_trailing_orphan_tool_calls(kept)

        if len(kept) < len(contents):
            note = types.Content(
                role="user",
                parts=[types.Part(text=_TRIM_NOTE)],
            )
            kept = [note, *kept]
            llm_request.contents = kept
            logger.info(
                "Context trimmed to fit window: %d -> %d messages (~%d/%d token budget)",
                len(contents),
                len(kept),
                total,
                available,
            )
        return None

    return before_model_callback
