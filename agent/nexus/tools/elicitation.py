# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Elicitation tools — ask_choice and suggest_options for eliciting user preference."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from nexus.tools._context import get_elicitation_callback, get_skip_confirmations
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)

_MAX_OPTIONS = 4
_MIN_OPTIONS = 2
_MAX_OPTION_CHARS = 70
_NUMBERED_LINE = re.compile(r"^\s*\d+[.)]\s+\S+")


def normalize_choice_options(raw: Any) -> list[str] | None:
    """Coerce a model-supplied options value into 2–4 unique short labels (2–6 words each)."""
    if raw is None or raw is False:
        return None
    values: list[Any]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text[:1] in "[{":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                values = parsed
            elif isinstance(parsed, dict):
                values = list(parsed.values())
            else:
                values = [line.strip() for line in text.splitlines() if line.strip()]
        else:
            values = [line.strip() for line in text.splitlines() if line.strip()]
    elif isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        return None

    labels: list[str] = []
    seen: set[str] = set()
    for item in values:
        label = " ".join(str(item or "").split())
        if not label:
            continue
        label = re.sub(r"^\d+[.)]\s+", "", label).strip()
        if not label:
            continue
        if len(label) > _MAX_OPTION_CHARS:
            label = label[: _MAX_OPTION_CHARS - 1] + "…"
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
        if len(labels) >= _MAX_OPTIONS:
            break
    return labels if len(labels) >= _MIN_OPTIONS else None


def normalize_suggestion_items(raw: Any) -> list[dict[str, str]] | None:
    """Coerce model-supplied items into a valid list of {name, description, action_label} dicts."""
    if raw is None:
        return None
    items_list: list[Any]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            items_list = parsed
        elif isinstance(parsed, dict):
            items_list = list(parsed.values())
        else:
            return None
    elif isinstance(raw, (list, tuple)):
        items_list = list(raw)
    else:
        return None

    normalized: list[dict[str, str]] = []
    for item in items_list:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split()).strip()
        desc = " ".join(str(item.get("description") or "").split()).strip()
        action = " ".join(str(item.get("action_label") or "Connect").split()).strip() or "Connect"
        if not name or not desc:
            continue
        normalized.append({
            "name": name,
            "description": desc,
            "action_label": action,
        })
    return normalized if normalized else None


def format_choice_history_text(question: str, options: list[str]) -> str:
    """Format the choice question plus numbered options for message history."""
    heading = (question or "").strip()
    if any(_NUMBERED_LINE.match(line) for line in heading.splitlines()):
        return heading
    numbered = "\n".join(f"{index}. {label}" for index, label in enumerate(options, start=1))
    return f"{heading}\n\n{numbered}"


def format_suggestion_history_text(title: str, items: list[dict[str, str]]) -> str:
    """Format suggestion items for message history."""
    heading = (title or "Suggested Options").strip()
    formatted_items = "\n".join(
        f"- {item['name']}: {item['description']} [{item['action_label']}]"
        for item in items
    )
    return f"{heading}\n\n{formatted_items}"


@normalized_tool
async def ask_choice(
    question: str,
    options: list[str],
    allow_free_text: bool = True,
) -> dict[str, Any]:
    """Ask the user a single clarifying question with selectable options.

    When you need the user's preference before you can proceed (not general chat),
    call `ask_choice` instead of asking in plain text.
    - Only call it when the answer changes what you do next.
    - One question at a time, max 4 options, short labels (2–6 words).
    - Never call it if the answer is already inferable from context — that's lazy, not careful.

    Args:
        question: A single, specific clarifying question.
        options: 2 to 4 short selectable options (2–6 words each).
        allow_free_text: Whether the user may type custom free text. Default is True.

    Returns:
        NormalizedToolResult with the user's selected choice or custom response.
    """
    clean_q = (question or "").strip()
    if not clean_q:
        return tool_error("question is required", error_code="INVALID_INPUT")
    if len(clean_q) > 600:
        clean_q = clean_q[:599] + "…"

    choices = normalize_choice_options(options)
    if not choices:
        return tool_error(
            "options must contain 2 to 4 distinct short labels (2–6 words each)",
            error_code="INVALID_INPUT",
        )

    if get_skip_confirmations():
        logger.info("ask_choice called during run with skip_confirmations; auto-resolving first choice")
        picked = choices[0]
        return tool_success(
            f"Auto-selected '{picked}' because skip_confirmations is active. Proceeding.",
            question=clean_q,
            selected=picked,
            options=choices,
        )

    callback = get_elicitation_callback()
    if callback is None:
        return tool_error(
            "ask_choice is not available in this run context. Continue with your "
            "best assumption and state it clearly in your final answer.",
            error_code="ELICITATION_UNAVAILABLE",
        )

    try:
        answer = await callback(
            mode="choice",
            question=clean_q,
            options=choices,
            allow_free_text=bool(allow_free_text),
        )
    except Exception as exc:
        logger.warning("ask_choice callback failed", exc_info=True)
        return tool_error(f"ask_choice failed: {exc}", error_code="ELICITATION_FAILED")

    if not answer:
        return tool_error(
            "The user did not select an option in time. Continue with your best assumption "
            "and state it clearly in your final answer.",
            error_code="TIMEOUT",
            suggested_alternatives=[],
        )

    return tool_success(
        f"User selected: {answer}",
        question=clean_q,
        selected=answer,
        options=choices,
    )


@normalized_tool
async def suggest_options(
    title: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Present a set of tools/integrations/products the user can pick from.

    When 2+ tools/integrations could fulfill a request and none is already active,
    call `suggest_options` so the user picks — don't silently choose one for them.

    Args:
        title: Title of the suggestion card (e.g. "Connectors that could help").
        items: List of tools/integrations/products to pick from. Each item should have:
            - name: Short display name (e.g. "Gmail", "Google Drive").
            - description: Brief explanation of what it does.
            - action_label: Label for the action button (default: "Connect").

    Returns:
        NormalizedToolResult with the user's choice or action confirmation.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        clean_title = "Connectors that could help"
    if len(clean_title) > 200:
        clean_title = clean_title[:199] + "…"

    normalized_items = normalize_suggestion_items(items)
    if not normalized_items:
        return tool_error(
            "items must contain at least one valid object with 'name' and 'description'",
            error_code="INVALID_INPUT",
        )

    if get_skip_confirmations():
        logger.info("suggest_options called during run with skip_confirmations; auto-resolving")
        first_item = normalized_items[0]["name"]
        return tool_success(
            f"Auto-selected '{first_item}' because skip_confirmations is active. Proceeding.",
            title=clean_title,
            selected=first_item,
            items=normalized_items,
        )

    callback = get_elicitation_callback()
    if callback is None:
        return tool_error(
            "suggest_options is not available in this run context. Continue with your "
            "best assumption and state it clearly in your final answer.",
            error_code="ELICITATION_UNAVAILABLE",
        )

    try:
        answer = await callback(
            mode="suggestion",
            title=clean_title,
            items=normalized_items,
        )
    except Exception as exc:
        logger.warning("suggest_options callback failed", exc_info=True)
        return tool_error(f"suggest_options failed: {exc}", error_code="ELICITATION_FAILED")

    if not answer:
        return tool_error(
            "The user did not pick an option in time. Continue with your best assumption "
            "and state it clearly in your final answer.",
            error_code="TIMEOUT",
            suggested_alternatives=[],
        )

    return tool_success(
        f"User selected: {answer}",
        title=clean_title,
        selected=answer,
        items=normalized_items,
    )
