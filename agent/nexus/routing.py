# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Cheap request routing before the full agent workflow starts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from nexus.runtime_config import SessionRuntimeConfig

logger = logging.getLogger(__name__)

RouteMode = Literal["ask", "search", "current", "work", "computer", "deep", "clarify", "capability"]


@dataclass(frozen=True)
class RouteDecision:
    mode: RouteMode
    needs_full_agent: bool
    reason: str
    clarification: str = ""


_WEB_RE = re.compile(
    r"\b(search|web search|google|look up|lookup|find online|latest|today|news|current|recent)\b",
    re.IGNORECASE,
)
_CURRENT_RE = re.compile(
    r"\b(today|tonight|now|live|latest|current|recent|score|scores|fixture|fixtures|schedule|match|matches|news|headline|headlines)\b",
    re.IGNORECASE,
)
_SPORTS_RE = re.compile(
    r"\b(ipl|cricket|bcci|icc|match|score|scores|fixture|fixtures|schedule|team|teams|vs|versus|toss|innings|football|soccer|nba|nfl|mlb|nhl|tennis|f1|formula 1)\b",
    re.IGNORECASE,
)
_DEEP_RE = re.compile(
    r"\b(research|investigate|compare|analysis|analyze|recommendation|report|deep dive|multi-source|sources)\b",
    re.IGNORECASE,
)
_COMPUTER_RE = re.compile(
    r"\b(click|desktop|screen|screenshot|gui|window|menu|dialog|drag|scroll|type into|open app|login|log in)\b",
    re.IGNORECASE,
)
_WORK_RE = re.compile(
    r"\b(implement|fix|edit|change|update|refactor|build|create|generate|write file|run|test|install|deploy|repo|code|commit|push|open localhost)\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(r"^\s*(what|who|when|where|why|how|is|are|do|does|can|could|should|explain|define)\b", re.IGNORECASE)
_DIRECT_QUESTION_RE = re.compile(r"^\s*(what|who|when|where|why|how|is|are|explain|define)\b", re.IGNORECASE)
_AMBIGUOUS_RE = re.compile(r"^\s*(fix|do|make|change|update|improve|handle|continue)\s+(it|this|that|them)\s*\.?\s*$", re.IGNORECASE)
_CAPABILITY_RE = re.compile(
    r"\b("
    r"do you have|can you use|can you access|are .*tools|what tools|which tools|"
    r"capabilities|features|integrations|connectors|mcp"
    r")\b",
    re.IGNORECASE,
)

_ROUTING_PROMPT = """You are the request router for CoComputer, an agentic system with full desktop control and specialized sub-agents.
Your goal is to choose the most efficient execution route for the user's request.

Available Routes:
- ask: Simple direct questions or conversational turns (hi, thanks) that don't need tools.
- search: Simple web lookups for static facts (who is, what is).
- current: Real-time queries like sports scores, news, or weather that need fresh web data.
- work: Local file-system tasks, coding, implementing features, or multi-step workflows.
- computer: GUI actions, clicking, typing into apps, screenshots, or visual navigation.
- deep: Complex research tasks requiring multiple sources, analysis, or long reports.
- capability: Questions about your own tools, features, connectors, or what you "can" do.
- clarify: Empty, nonsense, or extremely ambiguous requests (e.g. "fix it" with no context).

Decision Logic:
1. If the request mentions "click", "desktop", "screen", "screenshot", or visual apps -> "computer" (needs_full_agent=true).
2. If it asks to "implement", "fix code", "write file", or "run" -> "work" (needs_full_agent=true).
3. If it requires complex research or "deep dive" -> "deep" (needs_full_agent=true).
4. If it's a simple fact question -> "search" (needs_full_agent=false).
5. If it's a current event/score -> "current" (needs_full_agent=false).
6. If it's just "hi" or a direct question about a general concept -> "ask" (needs_full_agent=false).
7. If it asks "can you use Gmail?" or "what tools do you have?" -> "capability" (needs_full_agent=false).

Output your decision as JSON:
{{
  "mode": "route_name",
  "needs_full_agent": true/false,
  "reason": "short explanation",
  "clarification": "optional message if mode is clarify"
}}

User Request: {text}
Context: has_connectors={has_connectors}, has_uploads={has_uploads}"""


async def classify_request_llm(
    text: str,
    runtime_config: SessionRuntimeConfig | None = None,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Classify the request using Gemini Flash for improved accuracy."""
    if runtime_config is None or not runtime_config.gemini_available:
        # Fallback to simple logic if LLM is unavailable
        return classify_request_simple(text, has_connectors=has_connectors, has_uploads=has_uploads)

    prompt = _ROUTING_PROMPT.format(
        text=text.strip(),
        has_connectors=has_connectors,
        has_uploads=has_uploads,
    )

    try:
        from google.genai import types
        from nexus.runtime_config import build_genai_client

        model = runtime_config.gemini_light_model or "gemini-2.0-flash-exp"
        client = build_genai_client(runtime_config)

        def _generate():
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )

        response = await asyncio.to_thread(_generate)
        data = json.loads(response.text)
        
        return RouteDecision(
            mode=data.get("mode", "work"),
            needs_full_agent=bool(data.get("needs_full_agent", True)),
            reason=data.get("reason", "llm classification"),
            clarification=data.get("clarification", ""),
        )
    except Exception as exc:
        logger.warning("LLM routing failed, falling back to simple logic: %s", exc)
        return classify_request_simple(text, has_connectors=has_connectors, has_uploads=has_uploads)


def classify_request_simple(
    text: str,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Legacy regex-based routing used as a fallback."""
    cleaned = " ".join((text or "").split()).strip()
    lowered = cleaned.lower()

    if not cleaned:
        return RouteDecision("clarify", False, "empty request", "What do you want me to do?")

    if has_connectors or has_uploads:
        return RouteDecision("work", True, "selected context requires normal agent flow")

    if _AMBIGUOUS_RE.match(cleaned):
        return RouteDecision(
            "clarify",
            False,
            "ambiguous reference",
            "What exactly should I change or continue?",
        )

    word_count = len(cleaned.split())
    if _QUESTION_RE.match(cleaned) and word_count <= 80 and _CAPABILITY_RE.search(cleaned):
        return RouteDecision("capability", False, "capability question")

    if _DIRECT_QUESTION_RE.match(cleaned) and word_count <= 80 and not _WEB_RE.search(cleaned):
        return RouteDecision("ask", False, "simple direct question")

    if _DEEP_RE.search(cleaned):
        return RouteDecision("deep", True, "research or synthesis task")

    if _CURRENT_RE.search(cleaned) and (_SPORTS_RE.search(cleaned) or "news" in lowered or "headline" in lowered):
        return RouteDecision("current", False, "current sports/news lookup")

    if _COMPUTER_RE.search(cleaned):
        return RouteDecision("computer", True, "visual or GUI action requested")

    if _WORK_RE.search(cleaned):
        return RouteDecision("work", True, "local work or artifact creation requested")

    if _WEB_RE.search(cleaned):
        return RouteDecision("search", False, "simple web search")

    if "?" in cleaned or _QUESTION_RE.match(cleaned):
        if word_count <= 80:
            return RouteDecision("ask", False, "simple direct question")

    if word_count <= 20 and lowered in {"hi", "hello", "hey", "thanks", "thank you"}:
        return RouteDecision("ask", False, "simple conversational turn")

    return RouteDecision("work", True, "default to normal agent flow")


async def classify_request(
    text: str,
    runtime_config: SessionRuntimeConfig | None = None,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Return the cheapest safe execution route for a user request."""
    # Always prefer the LLM classifier for better accuracy
    return await classify_request_llm(
        text,
        runtime_config,
        has_connectors=has_connectors,
        has_uploads=has_uploads,
    )


def extract_search_query(text: str) -> str:
    """Strip common search prefixes without over-parsing the user's query."""
    query = " ".join((text or "").split()).strip()
    query = re.sub(
        r"^\s*(please\s+)?(web search|search web|search the web|search|google|look up|lookup|find online)\s+(for\s+)?",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    return query or text.strip()


def build_current_lookup_queries(text: str, *, date_label: str) -> list[str]:
    query = extract_search_query(text)
    lowered = query.lower()
    queries = [query]
    dated = f"{query} {date_label}"
    if dated.lower() != lowered:
        queries.append(dated)
    if "ipl" in lowered or "cricket" in lowered:
        queries.extend(
            [
                f"{query} site:iplt20.com",
                f"{query} site:espncricinfo.com",
                f"{query} site:cricbuzz.com",
            ]
        )
    elif "news" in lowered or "headline" in lowered:
        queries.extend(
            [
                f"{query} site:reuters.com",
                f"{query} site:apnews.com",
                f"{query} site:bbc.com",
            ]
        )
    deduped: list[str] = []
    seen: set[str] = set()
    for item in queries:
        normalized = " ".join(item.split()).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped[:5]
