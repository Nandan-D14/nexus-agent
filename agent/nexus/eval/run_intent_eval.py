# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Turn-intent eval: labelled follow-up / demand / error-inquiry cases.

Usage:
    python -m nexus.eval.run_intent_eval            # heuristics only (CI, deterministic)
    python -m nexus.eval.run_intent_eval --live     # heuristics + micro model on ambiguous

Heuristic mode gates only the ``clear`` cases (regex must decide those for
free). ``ambiguous`` cases document what the model path is expected to catch
and are scored only with ``--live``.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import sys

from nexus.config import settings
from nexus.intent import TurnIntent, classify_turn_intent, heuristic_intent

_PREVIOUS = "Create a 6-slide investor deck for Ledgerline and publish it"


@dataclass(frozen=True)
class IntentCase:
    text: str
    followup: bool = False
    demand: bool = False
    error: bool = False
    kind: str = "clear"
    previous_task: str = _PREVIOUS


INTENT_CASES: tuple[IntentCase, ...] = (
    IntentCase("continue", followup=True),
    IntentCase("ok", followup=True),
    IntentCase("go ahead", followup=True),
    IntentCase("create it", followup=True),
    IntentCase("try again", followup=True),
    IntentCase("continue and give ppt", followup=True, demand=True),
    IntentCase("where is my deck", demand=True),
    IntentCase("show me the presentation", demand=True),
    IntentCase("give ppt", demand=True),
    IntentCase("what went wrong", error=True),
    IntentCase("what was the error?", error=True),
    IntentCase("summarize my unread emails from today"),
    IntentCase("what is the weather in Paris"),
    IntentCase("do you have git and git cli"),
    IntentCase("Research the top CRM vendors and compare their pricing tiers in a table"),
    IntentCase("sounds good, ship it", followup=True, kind="ambiguous"),
    IntentCase("yes but make the theme dark blue", followup=True, kind="ambiguous"),
    IntentCase("perfect, finish the remaining slides", followup=True, kind="ambiguous"),
    IntentCase("did you finish? I can't find anything", demand=True, kind="ambiguous"),
    IntentCase("why is it broken", error=True, kind="ambiguous"),
)


def _matches(case: IntentCase, result: TurnIntent) -> bool:
    return (
        result.is_followup == case.followup
        and result.is_deliverable_demand == case.demand
        and result.is_error_inquiry == case.error
    )


async def evaluate(*, live: bool) -> list[tuple[IntentCase, TurnIntent]]:
    results = []
    for case in INTENT_CASES:
        if live:
            original = settings.intent_classifier_enabled
            settings.intent_classifier_enabled = True
            try:
                result = await classify_turn_intent(case.text, previous_task=case.previous_task)
            finally:
                settings.intent_classifier_enabled = original
        else:
            result = heuristic_intent(case.text)
        results.append((case, result))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CoComputer turn-intent eval")
    parser.add_argument("--live", action="store_true", help="use the micro-model classifier")
    args = parser.parse_args(argv)

    results = asyncio.run(evaluate(live=args.live))
    scored = [(case, result) for case, result in results if args.live or case.kind == "clear"]
    passed = [case for case, result in scored if _matches(case, result)]
    for case, result in scored:
        if not _matches(case, result):
            print(
                f"  MISMATCH {case.text!r}: followup={result.is_followup} "
                f"demand={result.is_deliverable_demand} error={result.is_error_inquiry} "
                f"(source={result.source})"
            )
    mode = "live" if args.live else "heuristic"
    print(f"intent eval ({mode}): {len(passed)}/{len(scored)} passed")
    if not args.live and len(passed) != len(scored):
        print("FAIL: heuristics must decide every clear case")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
