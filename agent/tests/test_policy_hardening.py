# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.policy import evaluate_tool_policy


def test_policy_requires_approval_for_git_history_destruction() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "git reset --hard HEAD~1"},
        autonomy_mode="auto",
    )

    assert decision.action == "require_approval"
    assert decision.risk == "high"


def test_policy_requires_approval_for_recursive_powershell_deletion() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "Remove-Item -Recurse -Force .next"},
        autonomy_mode="auto",
    )

    assert decision.action == "require_approval"
    assert decision.risk == "high"


def test_policy_requires_approval_for_production_deploy() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "vercel --prod --yes"},
        autonomy_mode="auto",
    )

    assert decision.action == "require_approval"
    assert decision.risk == "high"
