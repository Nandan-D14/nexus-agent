# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.policy import evaluate_tool_policy


def test_policy_allows_git_history_reset_in_sandbox() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "git reset --hard HEAD~1"},
        autonomy_mode="auto",
    )

    assert decision.action == "allow"
    assert decision.risk == "high"


def test_policy_allows_recursive_powershell_deletion_in_sandbox() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "Remove-Item -Recurse -Force .next"},
        autonomy_mode="auto",
    )

    assert decision.action == "allow"
    assert decision.risk == "high"


def test_policy_requires_approval_for_production_deploy_from_sandbox() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "vercel --prod --yes"},
        autonomy_mode="auto",
    )

    assert decision.action == "require_approval"
    assert decision.risk == "high"


def test_policy_denies_unbounded_find_root() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "find / -name '*.env'"},
        autonomy_mode="auto",
    )

    assert decision.action == "deny"
    assert decision.risk == "blocked"


def test_policy_denies_env_grep_for_keys() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "env | grep -i key"},
        autonomy_mode="auto",
    )

    assert decision.action == "deny"
    assert decision.risk == "blocked"


def test_policy_requires_approval_for_github_push_and_create_repo() -> None:
    push = evaluate_tool_policy("github_push", {"repo_name": "demo"}, autonomy_mode="auto")
    create = evaluate_tool_policy("github_create_repo", {"name": "demo"}, autonomy_mode="auto")
    clone = evaluate_tool_policy(
        "github_clone_repo",
        {"owner": "acme", "repo": "demo"},
        autonomy_mode="manual",
    )

    assert push.action == "require_approval"
    assert create.action == "require_approval"
    assert clone.action == "allow"


def test_policy_requires_approval_for_shell_git_push_from_sandbox() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "git push origin main"},
        autonomy_mode="auto",
    )

    assert decision.action == "require_approval"
    assert decision.risk == "high"


def test_policy_allows_workspace_listing() -> None:
    decision = evaluate_tool_policy(
        "run_command",
        {"command": "ls /workspace"},
        autonomy_mode="auto",
    )

    assert decision.action == "allow"
