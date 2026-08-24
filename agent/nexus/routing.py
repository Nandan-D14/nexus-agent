# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Legacy request routing shim.

The fast-path / mode router (ask / chat / search / current / clarify /
capability / artifact / work / computer / deep) was removed in the
full-agent-only migration — every user turn now goes through the single
planner. See ``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``.

This module is intentionally thin: it keeps the ``RouteDecision`` /
``RouteMode`` names so any external caller (evals, tests, notebooks) still
imports cleanly, but ``classify_request`` and ``classify_request_simple``
always return the same "route to full planner" decision. The planner prompt
itself performs the real triage.

New code should NOT depend on the return values here. The advisory
turn-budget classifier described in the migration plan (§5, Phase B) can be
added later without changing this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from nexus.runtime_config import SessionRuntimeConfig

RouteMode = Literal[
    "ask",
    "chat",
    "search",
    "current",
    "artifact",
    "work",
    "computer",
    "deep",
    "clarify",
    "capability",
]


@dataclass(frozen=True)
class RouteDecision:
    """Kept for backwards compatibility with tests and evals.

    ``needs_full_agent`` is always ``True`` — the fast path no longer
    exists.
    """

    mode: RouteMode
    needs_full_agent: bool
    reason: str
    clarification: str = ""


_FULL_AGENT_DECISION = RouteDecision(
    mode="work",
    needs_full_agent=True,
    reason="full-agent-only migration: single planner handles every turn",
)


async def classify_request(
    text: str,
    runtime_config: "SessionRuntimeConfig | None" = None,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Legacy async classifier. Always routes to the full planner."""
    del text, runtime_config, has_connectors, has_uploads
    return _FULL_AGENT_DECISION


async def classify_request_llm(
    text: str,
    runtime_config: "SessionRuntimeConfig | None" = None,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Legacy LLM classifier alias. Always routes to the full planner."""
    return await classify_request(
        text,
        runtime_config,
        has_connectors=has_connectors,
        has_uploads=has_uploads,
    )


def classify_request_simple(
    text: str,
    *,
    has_connectors: bool = False,
    has_uploads: bool = False,
) -> RouteDecision:
    """Legacy regex classifier. Always routes to the full planner."""
    del text, has_connectors, has_uploads
    return _FULL_AGENT_DECISION


def extract_search_query(text: str) -> str:
    """Return the user text unchanged (legacy helper retained for callers)."""
    return " ".join((text or "").split()).strip()


__all__ = [
    "RouteDecision",
    "RouteMode",
    "classify_request",
    "classify_request_llm",
    "classify_request_simple",
    "extract_search_query",
]
