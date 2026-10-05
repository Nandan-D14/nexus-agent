# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Deterministic turn heuristics: follow-ups, demands, markup dumps, soft vetoes.

Pure functions extracted from the orchestrator so routing (nexus.intent),
verification, and the turn loop share one implementation without importing
the orchestrator. ``nexus.orchestrator`` re-exports every name for callers.
"""

from __future__ import annotations

import re
from typing import Any

from nexus.control_loop import DELIVERABLE_DEMAND_RE
from nexus.prompt_safety import escape_internal_delimiters


# Short confirmations that are not a new task. "continue" / "create it" must
# resume the last substantial user request, not be verified as the whole job.
_SHORT_FOLLOWUP_RE = re.compile(
    r"^(?:"
    r"ok(?:ay|ie)?|yes|yep|yeah|sure|please|"
    r"go(?:\s+ahead)?|proceed|continue|retry|resume|"
    r"(?:keep|carry)\s+on|(?:keep|carry)\s+going|"
    r"try\s+again|do\s+it|do\s+that|do\s+this|"
    r"create\s+it|build\s+it|make\s+it|"
    r"go\s+on|next|again"
    r")(?:\s*[.!,])*$",
    re.IGNORECASE,
)
# "continue and give ppt" is still a confirmation of the prior task — but only
# when the message is short. A long "continue <new instructions>..." turn is a
# substantial request in its own right and must not be swallowed into a
# history reconstruction that buries the new details.
_SHORT_FOLLOWUP_PREFIX_RE = re.compile(
    r"^(?:continue|retry|resume|try\s+again)\b",
    re.IGNORECASE,
)
_SHORT_FOLLOWUP_PREFIX_MAX_CHARS = 80
_CREATE_OR_BUILD_RE = re.compile(
    r"\b(create|generate|build|make|export|produce|design|landing|vite|react|"
    r"website|webpage|prototype|app|pdf|xlsx|spreadsheet|docx|document|pptx?|"
    r"presentation|slides?|deck|report|artifact)\b",
    re.IGNORECASE,
)


def is_short_followup(text: str) -> bool:
    """Return True when *text* is a confirmation, not a new request."""
    stripped = str(text or "").strip()
    if _SHORT_FOLLOWUP_RE.match(stripped):
        return True
    return bool(
        len(stripped) <= _SHORT_FOLLOWUP_PREFIX_MAX_CHARS
        and _SHORT_FOLLOWUP_PREFIX_RE.match(stripped)
    )


_TASK_INQUIRY_RE = re.compile(
    r"\b(what('s| was| is) (my|the) task|what are we doing|remind me what|what was the task)\b",
    re.IGNORECASE,
)


def is_task_inquiry(text: str) -> bool:
    """Return True when the user is asking what their task was or inquiring about goals."""
    return bool(_TASK_INQUIRY_RE.search(str(text or "").strip()))


_ERROR_INQUIRY_RE = re.compile(
    r"what(?:'s| is| was)?\s+(the\s+)?error"
    r"|what went wrong"
    r"|why did\s+(it|that|this|the agent)\s+fail"
    r"|why\s+(the\s+)?error"
    r"|show\s+me\s+(the\s+)?error",
    re.IGNORECASE,
)


def is_error_inquiry(text: str) -> bool:
    """Return True when the user asks what the last turn's error was."""
    return bool(_ERROR_INQUIRY_RE.search(str(text or "").strip()))


def looks_like_create_or_build(text: str) -> bool:
    """Return True when the outstanding task still needs files or a preview."""
    return bool(_CREATE_OR_BUILD_RE.search(str(text or "")))


def looks_like_website_request(text: str) -> bool:
    """Return True when the request is a website/app page, not a PDF/Office file."""
    raw = str(text or "")
    if re.search(r"\b(pdf|xlsx|docx|pptx|spreadsheet)\b", raw, re.IGNORECASE) and not re.search(
        r"\b(website|webpage|landing|html|react|vite)\b", raw, re.IGNORECASE
    ):
        return False
    return bool(
        re.search(
            r"\b(website|webpage|landing|html|react|vite|dashboard)\b",
            raw,
            re.IGNORECASE,
        )
    )


def should_recover_website(error_code: str, request: str) -> bool:
    """Recover a published page when a website turn ended with no deliverable."""
    return error_code in {"MISSING_ARTIFACT", "MISSING_FINAL_RESPONSE"} and looks_like_website_request(
        request
    )


def is_deliverable_demand(text: str) -> bool:
    """Return True when the user is demanding a missing deliverable."""
    return bool(DELIVERABLE_DEMAND_RE.search(str(text or "").strip()))


_MARKUP_TAG_TOKENS = ("<section", "<!doctype html", "<html", "<article", "<div class=")
# python-pptx internals the model sometimes narrates instead of calling the tool.
_SLIDE_CODE_TOKENS = ("def kicker", "python-pptx", "add_textbox", "slide.shapes")
_CSS_DECLARATION_RE = re.compile(r"\b[a-z-]{3,}\s*:\s*[^;{}\n]{1,80};")


def looks_like_unpublished_markup(text: str) -> bool:
    """Return True when the model is dumping page source or slide code as chat.

    Structural only (tags, CSS declarations, pptx code identifiers). Product
    words like "invoice card" or "bento grid" are legitimate answer text and
    must never route a reply into hidden reasoning.
    """
    low = str(text or "").lower()
    if any(token in low for token in _MARKUP_TAG_TOKENS):
        return True
    if any(token in low for token in _SLIDE_CODE_TOKENS):
        return True
    if "grid-template-columns" in low:
        return True
    return len(_CSS_DECLARATION_RE.findall(low)) >= 3


_DECK_REQUEST_RE = re.compile(r"\b(pptx?|slides?|deck|presentation)\b", re.IGNORECASE)


def should_hide_markup(text: str, request: str = "") -> bool:
    """Route markup out of the answer stream only when it is a dump.

    For website/deck requests any markup is an unpublished deliverable (it is
    captured for recovery). Otherwise only bare markup with no fenced, explained
    code is hidden, so CSS/HTML/pptx help answers reach the user.
    """
    if not looks_like_unpublished_markup(text):
        return False
    req = str(request or "")
    if looks_like_website_request(req) or _DECK_REQUEST_RE.search(req):
        return True
    raw = str(text or "")
    if "```" in raw:
        return False
    stripped = raw.lstrip().lower()
    return stripped.startswith("<") or "<!doctype html" in stripped


def extract_html_dump(text: str) -> str:
    """Pull a publishable HTML fragment out of a chat/reasoning dump."""
    raw = str(text or "")
    fence = re.search(r"```(?:html)?\s*([\s\S]+?)```", raw, re.IGNORECASE)
    if fence and "<" in fence.group(1):
        chunk = fence.group(1).strip()
        if len(chunk) >= 200:
            return chunk
    start: int | None = None
    lowered = raw.lower()
    for marker in ("<!doctype html", "<html", "<section", "<article", "<div class="):
        index = lowered.find(marker)
        if index >= 0 and (start is None or index < start):
            start = index
    if start is None:
        return ""
    chunk = raw[start:].strip()
    return chunk if len(chunk) >= 200 else ""


def outstanding_user_task(messages: list[dict[str, Any]] | None, current: str) -> str:
    """Reconstruct the real task from prior user messages when *current* is short."""
    current_text = str(current or "").strip()
    substantial: list[str] = []
    seen: set[str] = set()
    for msg in reversed(messages or []):
        if str(msg.get("role") or "").lower() != "user":
            continue
        text = str(msg.get("text") or "").strip()
        if not text or is_short_followup(text) or is_task_inquiry(text) or is_deliverable_demand(text):
            continue
        if text.startswith("[SYSTEM") or text.startswith("[CONTINUE TASK]"):
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        substantial.append(text)
        if len(substantial) >= 3:
            break
    if not substantial:
        return current_text
    substantial.reverse()
    combined = "\n\n".join(substantial)
    if len(combined) > 2500:
        combined = combined[-2500:].lstrip()
    return combined


def format_continue_task(goal: str, confirmation: str = "") -> str:
    """Model-only task state for a message that continues earlier work.

    It never quotes or paraphrases the user (their message travels verbatim
    next to it); ``confirmation`` is kept for call compatibility.
    """
    del confirmation
    return (
        "[CONTINUE TASK]\n"
        "Outstanding request from earlier in this conversation:\n"
        f"{escape_internal_delimiters(goal.strip())}\n"
        "The user's latest message continues this request; finish it now using tools.\n"
        "If this is a website, landing page, or React/Vite app, write the files "
        "in the workspace, run the dev server bound to 0.0.0.0, and call "
        "publish_app_preview. If this is a PDF/XLSX/DOCX/PPTX, call "
        "terminal_worker with the matching generate_*_report tool and publish or "
        "save the resulting artifact.\n"
        "Then reply with a short status and the artifact or preview link.\n"
        "[END CONTINUE TASK]"
    )

# Pending background children are not an advisory caveat: delivering
# agent_complete would mark the durable run finished and skip the worker's
# wait-and-retry path in task_worker.py.
_HARD_INCOMPLETE_ERROR_CODES = frozenset({"SUBAGENTS_PENDING", "MISSING_ARTIFACT"})


def should_deliver_soft_veto(
    *,
    deliver_enabled: bool,
    final_response: str | None,
    status: str,
    error_code: str,
) -> bool:
    """Return True when an unverified turn may still be delivered as success."""
    if not deliver_enabled:
        return False
    if not (final_response and str(final_response).strip()):
        return False
    if status == "blocked":
        return False
    if error_code in _HARD_INCOMPLETE_ERROR_CODES:
        return False
    return True

