"""Cheap request routing before the full agent workflow starts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

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
    r"gmail|google calendar|calendar|google tasks|tasks|google drive|drive|connector|connectors|mcp"
    r")\b",
    re.IGNORECASE,
)


def classify_request(
    text: str,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Return the cheapest safe execution route for a user request."""
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
