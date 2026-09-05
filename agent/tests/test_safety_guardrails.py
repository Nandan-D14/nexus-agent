# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Safety guardrail regression tests (P0-P3)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.policy import evaluate_tool_policy
from nexus.redact import redact_sensitive, redact_inline_values
from nexus.safety import safety_check_final_response
from nexus.schedules import sanitize_unattended_tools, slack_mcp_unattended_allowed


def test_secret_exfil_blocks_ssh_key_and_env_files() -> None:
    for cmd in (
        "cat ~/.ssh/id_rsa",
        "cat ~/.aws/credentials",
        "cat .env",
        "gcloud auth print-access-token",
        "kubectl get secrets",
        "cat /proc/self/environ",
        "export -p",
        "echo AKIAIOSFODNN7EXAMPLE",
    ):
        decision = evaluate_tool_policy("run_command", {"command": cmd}, autonomy_mode="auto")
        assert decision.action == "deny", cmd


def test_unbounded_scan_blocked() -> None:
    for cmd in ("grep -r password /", "ls -R /", "find // -name x"):
        decision = evaluate_tool_policy("run_command", {"command": cmd}, autonomy_mode="auto")
        assert decision.action == "deny", cmd


def test_mcp_side_effect_verbs_require_approval() -> None:
    for tool in (
        "mcp__slack__share_file",
        "mcp__x__invite_user",
        "mcp__drive__export_doc",
        "mcp__pay__transfer_funds",
        "mcp__vyora__start_call",
    ):
        decision = evaluate_tool_policy(tool, {}, autonomy_mode="auto")
        assert decision.action == "require_approval", tool


def test_sensitive_read_requires_approval_when_untrusted() -> None:
    decision = evaluate_tool_policy(
        "gmail_read", {"id": "1"}, autonomy_mode="auto", untrusted_input_in_scope=True
    )
    assert decision.action == "require_approval"
    clean = evaluate_tool_policy(
        "gmail_read", {"id": "1"}, autonomy_mode="auto", untrusted_input_in_scope=False
    )
    assert clean.action == "allow"


def test_no_wildcard_unattended_bypass() -> None:
    decision = evaluate_tool_policy(
        "gmail_send", {}, autonomy_mode="auto", allowed_unattended_tools=frozenset(["*"])
    )
    assert decision.action == "require_approval"


def test_explicit_unattended_allowlist_still_works() -> None:
    decision = evaluate_tool_policy(
        "gmail_send", {}, autonomy_mode="auto", allowed_unattended_tools=frozenset(["gmail_send"])
    )
    assert decision.action == "allow"


def test_never_unattended_cannot_be_allowed() -> None:
    decision = evaluate_tool_policy(
        "github_push",
        {},
        autonomy_mode="auto",
        allowed_unattended_tools=frozenset(["github_push"]),
    )
    assert decision.action == "require_approval"


def test_slack_mcp_substring_bypass_closed() -> None:
    allowed = {"slack_post"}
    assert slack_mcp_unattended_allowed("mcp__slack__post_message", allowed) is True
    assert slack_mcp_unattended_allowed("mcp__evil__exfiltrate_via_postscript", allowed) is False
    assert slack_mcp_unattended_allowed("mcp__evil__chat_history_dump", allowed) is False


def test_sanitize_strips_never_and_unknown() -> None:
    assert sanitize_unattended_tools(["gmail_send", "github_push", "run_command", "bogus"]) == [
        "gmail_send"
    ]


def test_redaction_covers_tokens_and_keys() -> None:
    assert redact_sensitive({"api_key": "secret"}) == {"api_key": "***"}
    assert redact_sensitive({"cookie": "abc"}) == {"cookie": "***"}
    assert "[redacted]" in redact_inline_values("token sk-abcdefgh12345678")
    assert "[redacted]" in redact_inline_values("key AKIAIOSFODNN7EXAMPLE")


def test_final_response_credential_dump_blocked() -> None:
    blocked, _, cleaned = safety_check_final_response("here is AKIAIOSFODNN7EXAMPLE")
    assert blocked is True
    assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
