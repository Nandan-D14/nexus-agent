# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Structured completion contract for the planner.

``report_completion`` lets the planner declare the outcome as data instead of
prose. The completion verifier checks those claims against the action ledger
(claimed artifacts must exist, partial/blocked must be honest) rather than
regex-matching phrases like "successfully created" in the final text. Claimed
artifacts are stored under ``claimed_artifacts`` — never ``artifacts`` — so a
claim can never count as its own proof.
"""

from __future__ import annotations

from typing import Any, Literal

from nexus.tools.base import normalized_tool, tool_error, tool_success

_MAX_ITEMS = 12


def _clean_list(values: Any, *, limit: int = 300) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    cleaned = [str(item).strip()[:limit] for item in values if str(item or "").strip()]
    return cleaned[:_MAX_ITEMS]


@normalized_tool
async def report_completion(
    status: Literal["completed", "partial", "blocked"],
    summary: str,
    artifacts: list[str] | None = None,
    evidence: list[str] | None = None,
    remaining: list[str] | None = None,
) -> dict[str, Any]:
    """Declare the task outcome right before your final reply (tool tasks only).

    Call once per turn after the work is done and observed. Be honest: the
    runtime checks every claim against what tools actually produced.

    Args:
        status: completed (deliverable exists and was verified), partial
            (some work remains), or blocked (needs the user/approval/access).
        summary: One or two sentences describing the outcome.
        artifacts: Exact artifact ids, file paths, or URLs produced this turn.
        evidence: Short observed facts proving the outcome (exit codes,
            verified screenshots, row counts, HTTP status).
        remaining: Work still outstanding (required for partial/blocked).

    Returns:
        NormalizedToolResult echoing the recorded contract.
    """
    clean_status = str(status or "").strip().lower()
    if clean_status not in {"completed", "partial", "blocked"}:
        return tool_error(
            "status must be completed, partial, or blocked.",
            error_code="INVALID_INPUT",
        )
    clean_remaining = _clean_list(remaining, limit=500)
    if clean_status != "completed" and not clean_remaining:
        return tool_error(
            "List the remaining work for a partial or blocked outcome.",
            error_code="INVALID_INPUT",
        )
    contract = {
        "status": clean_status,
        "summary": str(summary or "").strip()[:1000],
        "claimed_artifacts": _clean_list(artifacts),
        "evidence": _clean_list(evidence),
        "remaining": clean_remaining,
    }
    return tool_success(
        f"Completion recorded: {clean_status}.",
        detail={"completion_contract": contract},
        completion_contract=contract,
    )


__all__ = ["report_completion"]
