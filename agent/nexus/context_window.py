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
from collections import Counter
from typing import Any

from google.genai import types

from nexus.config import settings

logger = logging.getLogger(__name__)

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


def _tool_part_keys(content, attribute: str) -> Counter[tuple[str, str]]:
    """Return stable ids (or names) for function-call/response parts."""
    values = [
        getattr(part, attribute, None)
        for part in (getattr(content, "parts", None) or [])
    ]
    tools = [value for value in values if value is not None]
    if tools and all(str(getattr(tool, "id", "") or "").strip() for tool in tools):
        return Counter(("id", str(getattr(tool, "id"))) for tool in tools)
    return Counter(
        ("name", str(getattr(tool, "name", "") or ""))
        for tool in tools
    )


def _tool_turns_match(call_content, response_content) -> bool:
    calls = _tool_part_keys(call_content, "function_call")
    responses = _tool_part_keys(response_content, "function_response")
    if not calls or not responses:
        return False
    if all(kind == "id" for kind, _ in calls) and all(
        kind == "id" for kind, _ in responses
    ):
        return calls == responses
    call_names = _tool_part_keys(call_content, "function_call")
    response_names = _tool_part_keys(response_content, "function_response")
    # One side may have ids while the other does not. Compare names then.
    if any(kind == "id" for kind, _ in call_names):
        call_names = Counter(
            ("name", str(getattr(part.function_call, "name", "") or ""))
            for part in (getattr(call_content, "parts", None) or [])
            if getattr(part, "function_call", None) is not None
        )
    if any(kind == "id" for kind, _ in response_names):
        response_names = Counter(
            ("name", str(getattr(part.function_response, "name", "") or ""))
            for part in (getattr(response_content, "parts", None) or [])
            if getattr(part, "function_response", None) is not None
        )
    return call_names == response_names


def _unanswered_function_calls(call_content, response_content) -> list | None:
    """Return calls missing responses, or None when responses do not belong."""
    calls = [
        part.function_call
        for part in (getattr(call_content, "parts", None) or [])
        if getattr(part, "function_call", None) is not None
    ]
    responses = [
        part.function_response
        for part in (getattr(response_content, "parts", None) or [])
        if getattr(part, "function_response", None) is not None
    ]
    if not calls or not responses:
        return None
    use_ids = all(str(getattr(tool, "id", "") or "").strip() for tool in calls + responses)

    def key(tool) -> str:
        field = "id" if use_ids else "name"
        return str(getattr(tool, field, "") or "")

    remaining = Counter(key(call) for call in calls)
    for response in responses:
        response_key = key(response)
        if remaining[response_key] <= 0:
            return None
        remaining[response_key] -= 1

    unanswered = []
    for call in calls:
        call_key = key(call)
        if remaining[call_key] > 0:
            unanswered.append(call)
            remaining[call_key] -= 1
    return unanswered


def _interrupted_response_part(call) -> types.Part:
    return types.Part(
        function_response=types.FunctionResponse(
            id=getattr(call, "id", None),
            name=str(getattr(call, "name", "") or ""),
            response={
                "status": "error",
                "error_code": "TOOL_INTERRUPTED",
                "summary": (
                    "Tool execution was interrupted before a result was recorded. "
                    "Verify state before retrying."
                ),
                "retryable": True,
            },
        )
    )


def _repair_unpaired_tool_turns(contents: list) -> list:
    """Heal interrupted tool turns anywhere in model context.

    A process restart can persist an assistant ``function_call`` but not its
    response. Once the user sends another message, that orphan is no longer at
    the tail, so a trailing-only repair misses it and providers reject every
    later turn with "Missing tool result". Keep the call and inject a matching
    error response so the model knows the side effect is unverified and can
    safely retry. Valid call/response pairs must be adjacent in model history.
    """
    repaired: list = []
    index = 0
    while index < len(contents):
        content = contents[index]
        if _has_function_call(content):
            next_content = contents[index + 1] if index + 1 < len(contents) else None
            if next_content is not None and _has_function_response(next_content):
                unanswered = _unanswered_function_calls(content, next_content)
                if unanswered is not None:
                    if not unanswered:
                        repaired.extend((content, next_content))
                    else:
                        repaired.extend(
                            (
                                content,
                                types.Content(
                                    role=getattr(next_content, "role", None) or "user",
                                    parts=[
                                        *(getattr(next_content, "parts", None) or []),
                                        *[
                                            _interrupted_response_part(call)
                                            for call in unanswered
                                        ],
                                    ],
                                ),
                            )
                        )
                    index += 2
                    continue
            interrupted_parts = [
                _interrupted_response_part(part.function_call)
                for part in (getattr(content, "parts", None) or [])
                if getattr(part, "function_call", None) is not None
            ]
            repaired.append(content)
            if interrupted_parts:
                repaired.append(types.Content(role="user", parts=interrupted_parts))
            index += 1
            continue
        if _has_function_response(content):
            index += 1
            continue
        repaired.append(content)
        index += 1
    return repaired


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
    "publish_app_preview",
    "ask_choice",
    "suggest_options",
    "generate_pdf_report",
    "generate_docx_report",
    "save_as_artifact",
    "extract_pdf_text",
    "extract_document_text",
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


def _filter_tools_to_allowlist(tools: list) -> tuple[list, list[str]]:
    """Hide declarations the gateway would refuse to execute anyway.

    The allowlist was only enforced at call time, so the model still saw every
    tool and could burn a whole turn picking one that comes back as
    ``TOOL_NOT_SELECTED``. Removing them from the schema makes the user's tool
    selection actually steer the model, and shrinks the prompt as a side effect.
    """
    from nexus.tool_catalog import is_tool_allowed
    from nexus.tools._context import get_tool_allowlist

    allowlist = get_tool_allowlist()
    if allowlist is None:
        return tools, []

    current = list(tools)
    hidden: list[str] = []
    for tool_index in range(len(current) - 1, -1, -1):
        decls = list(getattr(current[tool_index], "function_declarations", None) or [])
        if not decls:
            continue
        kept = []
        for decl in decls:
            name = str(getattr(decl, "name", "") or "")
            if name and not is_tool_allowed(name, allowlist):
                hidden.append(name)
            else:
                kept.append(decl)
        if len(kept) == len(decls):
            continue
        if kept:
            current[tool_index].function_declarations = kept
        else:
            current.pop(tool_index)
    return current, hidden


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
        repaired_contents = _repair_unpaired_tool_turns(contents)
        if repaired_contents != contents:
            logger.warning(
                "Repaired unpaired tool history before model call (%d -> %d messages)",
                len(contents),
                len(repaired_contents),
            )
            llm_request.contents = repaired_contents
            contents = repaired_contents
        sys_tok = _estimate_system_tokens(llm_request)
        content_tok = sum(_estimate_tokens_for_content(c) for c in contents)
        limit, budget = _input_token_budget(runtime_config)
        cfg = getattr(llm_request, "config", None)
        tools = getattr(cfg, "tools", None) if cfg else None
        tool_list = list(tools) if isinstance(tools, list) else []

        # Apply the user's tool selection to the schema, not just to execution.
        # Runs before budgeting so the pruner only has to consider real options.
        if cfg is not None and tool_list:
            try:
                tool_list, hidden_tools = _filter_tools_to_allowlist(tool_list)
            except Exception:
                # Never brick a turn over schema filtering; the gateway still gates.
                logger.debug("Tool allowlist filtering failed", exc_info=True)
                hidden_tools = []
            if hidden_tools:
                cfg.tools = tool_list
                logger.info(
                    "Hid %d unselected tool schemas from the model", len(hidden_tools)
                )

        tool_tok = _estimate_tokens_for_tools(tool_list)
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
        # Trimming may split a formerly valid tool pair at the budget boundary.
        kept = _repair_unpaired_tool_turns(kept)

        if kept != contents:
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
