# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""CI gate for the routing eval (full-agent-only migration).

After the fast-path / mode-router removal
(``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``) the only invariant is that every
request routes to the full planner. This gate enforces 100% agreement.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.eval.run_routing_eval import evaluate, summarize


class RoutingEvalGateTests(TestCase):
    def test_every_case_routes_to_full_planner(self) -> None:
        results = asyncio.run(evaluate(use_llm=False))
        accuracy, _ = summarize(results)
        mismatches = [r.case.text for r in results if not r.passed]
        self.assertEqual(
            accuracy,
            1.0,
            msg=f"full-agent invariant broken; mismatches={mismatches}",
        )
