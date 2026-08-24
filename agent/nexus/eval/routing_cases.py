# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Golden routing dataset — full-agent-only migration.

The fast path (ask / chat / search / current / clarify / capability) and the
artifact mini-agent were removed
(``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``). This dataset now only pins one
invariant: every realistic user turn routes to the full planner
(``needs_full_agent=True``).

When the Phase B turn-budget classifier lands (simple / standard / deep),
extend ``RoutingCase`` with an ``expected_tier`` field — the ``expected_mode``
column is retained for readability but is no longer enforced by the eval.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoutingCase:
    text: str
    expected_mode: str
    expects_full_agent: bool
    note: str = ""
    has_connectors: bool = False
    has_uploads: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


# All realistic turns should route through the planner. Cases are grouped by
# the *kind* of ask so a future budget-tier classifier has a natural mapping,
# but ``expects_full_agent=True`` is the only value checked today.
CONVERSATIONAL_CASES: list[RoutingCase] = [
    RoutingCase("What is Python?", "work", True, tags=("conversational",)),
    RoutingCase("Explain how TCP works", "work", True, tags=("conversational",)),
    RoutingCase("hi", "work", True, tags=("conversational",)),
    RoutingCase("thanks", "work", True, tags=("conversational",)),
    RoutingCase("do you have gmail and other tools?", "work", True, tags=("capability",)),
    RoutingCase("what tools can you use?", "work", True, tags=("capability",)),
]

SEARCH_CURRENT_CASES: list[RoutingCase] = [
    RoutingCase("search web for Gemini docs", "work", True, tags=("search",)),
    RoutingCase("look up the population of Japan", "work", True, tags=("search",)),
    RoutingCase("what is today's IPL match?", "work", True, tags=("current",)),
    RoutingCase("latest AI news today", "work", True, tags=("current",)),
    RoutingCase("what's the score in the cricket match right now", "work", True, tags=("current",)),
]

DELIVERABLE_CASES: list[RoutingCase] = [
    RoutingCase("Create a simple calculator", "work", True, tags=("html",)),
    RoutingCase("Build a to-do list tool as a single page", "work", True, tags=("html",)),
    RoutingCase("Make a pricing table html page", "work", True, tags=("html",)),
    RoutingCase("research FIFA 2026 stats and give me a PDF", "work", True, tags=("pdf",)),
    RoutingCase("export a monthly expenses xlsx from this data", "work", True, tags=("xlsx",)),
]

SANDBOX_WORK_CASES: list[RoutingCase] = [
    RoutingCase("Build a Next.js calculator app", "work", True, tags=("dev-app",)),
    RoutingCase("fix the repo tests and update the code", "work", True, tags=("code",)),
    RoutingCase("install the dependencies and run the dev server", "work", True, tags=("code",)),
    RoutingCase("commit and push my changes", "work", True, tags=("code",)),
    RoutingCase("refactor the auth module and add tests", "work", True, tags=("code",)),
]

GUI_CASES: list[RoutingCase] = [
    RoutingCase("click the login button on the desktop", "work", True, tags=("gui",)),
    RoutingCase("take a screenshot of the current screen", "work", True, tags=("gui",)),
    RoutingCase("open the settings app and change the theme", "work", True, tags=("gui",)),
    RoutingCase("drag the file into the trash", "work", True, tags=("gui",)),
]

RESEARCH_CASES: list[RoutingCase] = [
    RoutingCase("research today's news from five sources", "work", True, tags=("research",)),
    RoutingCase("compare the top 3 vector databases and give a recommendation", "work", True, tags=("research",)),
    RoutingCase("investigate why our latency regressed and write a report", "work", True, tags=("research",)),
    RoutingCase("do a deep dive analysis of the electric vehicle market", "work", True, tags=("research",)),
    RoutingCase("summarize https://example.com/post and cite sources", "work", True, tags=("research",)),
    RoutingCase("search for Gemini docs and explain the main changes", "work", True, tags=("research",)),
    RoutingCase("look up three sources about RAG and compare them", "work", True, tags=("research",)),
]

AMBIGUOUS_CASES: list[RoutingCase] = [
    RoutingCase("fix it", "work", True, tags=("ambiguous",)),
    RoutingCase("do this", "work", True, tags=("ambiguous",)),
    RoutingCase("continue", "work", True, tags=("ambiguous",)),
]

CONTEXT_CASES: list[RoutingCase] = [
    RoutingCase(
        "summarize my latest emails",
        "work",
        True,
        has_connectors=True,
        note="selected connector context still requires full agent",
        tags=("context",),
    ),
    RoutingCase(
        "what does this file say",
        "work",
        True,
        has_uploads=True,
        note="uploaded file still requires full agent",
        tags=("context",),
    ),
]


ALL_CASES: list[RoutingCase] = [
    *CONVERSATIONAL_CASES,
    *SEARCH_CURRENT_CASES,
    *DELIVERABLE_CASES,
    *SANDBOX_WORK_CASES,
    *GUI_CASES,
    *RESEARCH_CASES,
    *AMBIGUOUS_CASES,
    *CONTEXT_CASES,
]


__all__ = ["RoutingCase", "ALL_CASES"]
