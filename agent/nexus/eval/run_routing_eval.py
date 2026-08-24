# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Routing eval runner — full-agent-only sanity check.

Usage:
    python -m nexus.eval.run_routing_eval          # deterministic (shim)
    python -m nexus.eval.run_routing_eval --llm    # LLM shim (still routes all → planner)

After the fast-path / mode-router removal (see
``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``), routing collapsed to a single
invariant: every user turn routes to the full planner. This eval enforces
exactly that. When the Phase B turn-budget classifier lands, extend this
runner to compare ``expected_tier`` instead.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from dataclasses import dataclass

from nexus.eval.routing_cases import ALL_CASES, RoutingCase
from nexus.routing import classify_request, classify_request_simple


@dataclass
class CaseResult:
    case: RoutingCase
    actual_mode: str
    actual_full_agent: bool

    @property
    def full_agent_ok(self) -> bool:
        return self.actual_full_agent == self.case.expects_full_agent

    @property
    def passed(self) -> bool:
        return self.full_agent_ok


async def _classify(case: RoutingCase, *, use_llm: bool) -> CaseResult:
    if use_llm:
        decision = await classify_request(
            case.text,
            has_connectors=case.has_connectors,
            has_uploads=case.has_uploads,
        )
    else:
        decision = classify_request_simple(
            case.text,
            has_connectors=case.has_connectors,
            has_uploads=case.has_uploads,
        )
    return CaseResult(case, decision.mode, decision.needs_full_agent)


async def evaluate(*, use_llm: bool) -> list[CaseResult]:
    return [await _classify(case, use_llm=use_llm) for case in ALL_CASES]


def summarize(results: list[CaseResult]) -> tuple[float, dict[str, tuple[int, int]]]:
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        bucket = r.case.tags[0] if r.case.tags else r.case.expected_mode
        by_tag[bucket].append(r.passed)
    per_tag = {tag: (sum(v), len(v)) for tag, v in sorted(by_tag.items())}
    total_pass = sum(1 for r in results if r.passed)
    accuracy = total_pass / len(results) if results else 0.0
    return accuracy, per_tag


def report(results: list[CaseResult], accuracy: float, per_tag: dict[str, tuple[int, int]]) -> None:
    print("\n=== Routing eval scoreboard (full-agent-only) ===\n")
    print(f"{'bucket':<16}{'pass':>6}{'total':>7}{'acc':>8}")
    print("-" * 37)
    for tag, (passed, total) in per_tag.items():
        acc = passed / total if total else 0.0
        print(f"{tag:<16}{passed:>6}{total:>7}{acc:>7.0%}")
    print("-" * 37)
    print(f"{'OVERALL':<16}{sum(p for p, _ in per_tag.values()):>6}{len(results):>7}{accuracy:>7.0%}\n")

    mismatches = [r for r in results if not r.passed]
    if mismatches:
        print(f"{len(mismatches)} mismatch(es):\n")
        for r in mismatches:
            print(
                f"  - {r.case.text!r}: full_agent={r.actual_full_agent} "
                f"expected={r.case.expects_full_agent}"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoComputer routing eval")
    parser.add_argument("--llm", action="store_true", help="use the (shim) LLM router")
    parser.add_argument("--min", type=float, default=1.00, help="minimum overall accuracy to pass")
    args = parser.parse_args(argv)

    results = asyncio.run(evaluate(use_llm=args.llm))
    accuracy, per_tag = summarize(results)
    report(results, accuracy, per_tag)

    if accuracy < args.min:
        print(f"FAIL: accuracy {accuracy:.0%} < required {args.min:.0%}")
        return 1
    print(f"PASS: accuracy {accuracy:.0%} >= required {args.min:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
