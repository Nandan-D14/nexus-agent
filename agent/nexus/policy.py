# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Tool safety policy for manual and Auto Mode execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

AutonomyMode = Literal["manual", "auto"]
PolicyAction = Literal["allow", "require_approval", "deny"]


_EXTERNAL_SIDE_EFFECT_TOOLS = {
    "gmail_send",
    "calendar_create",
    "calendar_update",
    "calendar_delete",
    "tasks_create",
    "github_create_issue",
    "github_create_repo",
    "github_push",
    "vyora_start_call",
    "upload_drive_file",
    "create_drive_doc",
    "create_drive_sheet",
    "schedules_create",
}

_SENSITIVE_READ_TOOLS = {
    "gmail_read",
    "read_drive_file",
    "github_read_file",
}

_DESTRUCTIVE_COMMAND_RE = re.compile(
    r"(?is)(\brm\s+(?:-[^;\n]*[rf]|--recursive|--force)|"
    r"\brm\$\{[^}]*\}-[^;\n]*[rf]|"
    r"\bxargs\b[^;\n]*\brm\b|"
    r"\bfind\b[^;\n]*-(?:delete|exec\s+rm)|"
    r"\b(?:unlink|shred)\b|"
    r"\bRemove-Item\b(?:(?!\s*-WhatIf\b)[^;\n]*(-Recurse|-Force))?|"
    r"\b(?:rmdir|rd)\b[^;\n]*(?:/s|-r|/q)|"
    r"\b(?:del|erase)\b[^;\n]*(?:/s|/q|\s+[A-Za-z]:[\\/]|\s+\S+\.\S+)|"
    r"\b(?:sudo|su|runas)\b|"
    r"\b(?:mkfs|fdisk|parted|mkswap)\b|"
    r"\bdd\s+(?:if=|of=)|"
    r"\b(?:shutdown|poweroff|halt|reboot|init\s+0)\b|"
    r"\b(?:killall|pkill)\b|"
    r"\bkill\s+-9\s+1\b|"
    r"\bchmod\s+-R\s+777\b|"
    r"\b(?:chmod\s+\+x|chown\s+-R|chattr)\b|"
    r"\bgit\s+reset\s+--hard\b|"
    r"\bgit\s+clean\s+-[^;\n]*[fd]|"
    r"\bgit\s+(?:branch\s+-D|checkout\s+--\s+\.|restore\s+--source)|"
    r"\bdrop\s+(?:database|schema|table)\b|"
    r"\btruncate\s+table\b|"
    r"\b(?:kubectl\s+delete|terraform\s+destroy|docker\s+system\s+prune)\b|"
    r"\bvercel\b[^;\n]*--prod\b|"
    r"\b(?:firebase|gcloud\s+app)\s+deploy\b|"
    r"\bcurl\b[^;\n|]*\|\s*(?:sh|bash|python|pwsh|powershell)|"
    r"\bwget\b[^;\n|]*\|\s*(?:sh|bash|python|pwsh|powershell)|"
    r"Invoke-WebRequest[^;\n]*\|\s*(?:iex|Invoke-Expression)|"
    r"\b(?:certutil|bitsadmin)\b|"
    r"\bnpm\b[^;\n]*-g\s+install\b)"
)

_SECRET_EXFIL_RE = re.compile(
    r"(?is)(GOOGLE_APPLICATION_CREDENTIALS|"
    r"googleDriveRefreshToken|"
    r"refresh_token|"
    r"api[_-]?key|"
    r"authorization|"
    r"bearer\s+[A-Za-z0-9._-]+|"
    r"\.config/rclone|"
    r"userPrivate|"
    r"\.ssh/id_rsa|"
    r"\.aws/credentials|"
    r"\.docker/config\.json|"
    r"\.pem\b|"
    r"\.env\b|"
    r"secrets\.json|"
    r"BEGIN\s+PRIVATE\s+KEY|"
    r"AKIA[0-9A-Z]{16}|"
    r"gh[pousr]_[A-Za-z0-9_]+|"
    r"xox[bap]-|"
    r"ya29\.|"
    r"client_secret|"
    r"private_key|"
    r"gcloud\s+auth\s+print|"
    r"aws\s+sts|"
    r"vault\s+read|"
    r"kubectl\s+get\s+secrets?|"
    r"gh\s+auth\s+token|"
    r"\bcat\s+/proc/self/environ\b|"
    r"(?:^|[;&|\s])(?:env|set|export\s+-p|declare\s+-x)\b|"
    r"\benv\b[\s\S]{0,80}\bgrep\b|"
    r"\bprintenv\b)"
)
_UNBOUNDED_FIND_RE = re.compile(
    r"(?is)(?:\bfind\s+/(?:\s|$|;)|\bfind\s+//|\bfind\s+\$HOME/\.\.|\bgrep\s+-r[^;\n]*\s+/|\bls\s+-R\s+/|\bdu\s+-[a-z]*s?\s+/|\btar\s+-[a-z]*c[a-z]*\s+\S+\s+/(?:\s|$|;))"
)
_MCP_SIDE_EFFECT_RE = re.compile(
    r"(?:^|_)(create|update|delete|remove|destroy|write|drop|deploy|"
    r"send|upload|insert|execute|run|publish|post|put|patch|share|invite|"
    r"forward|export|download|copy|schedule|subscribe|transfer|pay|purchase|"
    r"call|start)(?:_|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ToolPolicyDecision:
    action: PolicyAction
    reason: str
    risk: Literal["low", "medium", "high", "blocked"] = "low"


def normalize_autonomy_mode(value: str | None) -> AutonomyMode:
    return "auto" if str(value or "").strip().lower() == "auto" else "manual"


def evaluate_tool_policy(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    autonomy_mode: str | None = None,
    untrusted_input_in_scope: bool = False,
    allowed_unattended_tools: frozenset[str] | set[str] | None = None,
) -> ToolPolicyDecision:
    """Return the policy decision for a tool call before execution.

    Manual mode still allows low-risk local work. Auto Mode removes approval for
    medium-risk actions, but high-impact external/destructive actions remain gated.
    Scheduled runs may skip approval for an explicit unattended allowlist.
    """
    from nexus.schedules import NEVER_UNATTENDED_TOOLS, slack_mcp_unattended_allowed

    normalized_tool = (tool_name or "").strip()
    mode = normalize_autonomy_mode(autonomy_mode)
    args = args or {}
    allowed = {str(item).strip() for item in (allowed_unattended_tools or set()) if str(item).strip()}

    if normalized_tool == "run_command":
        command = str(args.get("command") or "")
        if _SECRET_EXFIL_RE.search(command):
            return ToolPolicyDecision(
                "deny",
                "Command appears to read or expose credentials/secrets.",
                "blocked",
            )
        if _UNBOUNDED_FIND_RE.search(command):
            return ToolPolicyDecision(
                "deny",
                "Unbounded filesystem walk (find /) is not allowed. Search a specific directory.",
                "blocked",
            )
        # External-persistence shell escapes always need approval, even in the
        # sandbox: they push state outside the disposable VM.
        if re.search(
            r"(?is)(\bgit\s+push\b|\bvercel\b[^;\n]*--prod\b|"
            r"\b(?:firebase|gcloud\s+app)\s+deploy\b|"
            r"\bgh\s+repo\s+(?:create|fork)\b|\bgit\s+push\s+--force\b)",
            command,
        ):
            return ToolPolicyDecision(
                "require_approval",
                "Shell command publishes outside the sandbox and requires approval.",
                "high",
            )
        # Sandbox-local destructives stay approval-free: the E2B VM is
        # disposable. Risk is still labeled for log visibility.
        if _DESTRUCTIVE_COMMAND_RE.search(command):
            return ToolPolicyDecision(
                "allow",
                "Sandbox command allowed without approval.",
                "high",
            )
        return ToolPolicyDecision("allow", "Low-risk shell command.", "medium")

    # High-impact external/MCP side effects stay gated even on unattended runs.
    # This check runs before the unattended allowlist so skip_confirmations or
    # "*" cannot bypass it (except tools explicitly in the unattended allowlist
    # handled below via NEVER_UNATTENDED_TOOLS exclusion).
    if normalized_tool.startswith("mcp__"):
        remote_name = normalized_tool.rsplit("__", 1)[-1]
        if _MCP_SIDE_EFFECT_RE.search(remote_name):
            return ToolPolicyDecision(
                "require_approval",
                "Remote MCP side effects require user confirmation.",
                "high",
            )

    try:
        from nexus.tools._context import get_skip_confirmations

        skip_conf = get_skip_confirmations()
    except Exception:
        skip_conf = False

    # Explicit unattended allowlist only — no skip_confirmations wildcard and
    # no "*" bypass. skip_conf alone never auto-allows; the scheduler must pass
    # an explicit per-schedule allowlist.
    explicit_unattended = (
        normalized_tool in allowed
        or slack_mcp_unattended_allowed(normalized_tool, allowed)
    ) and normalized_tool not in NEVER_UNATTENDED_TOOLS
    if explicit_unattended:
        # NEVER tools already excluded above; double-guard here.
        if normalized_tool not in NEVER_UNATTENDED_TOOLS:
            return ToolPolicyDecision(
                "allow",
                "Allowed by scheduled unattended-tool auto-approval.",
                "low",
            )

    if normalized_tool in NEVER_UNATTENDED_TOOLS:
        # Never auto-approve these, even on unattended runs. External ones
        # still surface as approval gates in interactive mode.
        if normalized_tool in _EXTERNAL_SIDE_EFFECT_TOOLS:
            return ToolPolicyDecision(
                "require_approval",
                "External side-effect tools require user confirmation.",
                "high",
            )

    if normalized_tool.startswith("mcp__"):
        remote_name = normalized_tool.rsplit("__", 1)[-1]
        if _MCP_SIDE_EFFECT_RE.search(remote_name):
            return ToolPolicyDecision(
                "require_approval",
                "Remote MCP side effects require user confirmation.",
                "high",
            )
        if mode == "manual":
            return ToolPolicyDecision(
                "require_approval",
                "Manual mode requires approval for remote MCP connector calls.",
                "medium",
            )
        return ToolPolicyDecision(
            "allow",
            "Read-only MCP call allowed in Auto Mode.",
            "low",
        )

    if normalized_tool in _EXTERNAL_SIDE_EFFECT_TOOLS:
        return ToolPolicyDecision(
            "require_approval",
            "External side-effect tools require user confirmation.",
            "high",
        )

    if normalized_tool in _SENSITIVE_READ_TOOLS and untrusted_input_in_scope:
        return ToolPolicyDecision(
            "require_approval",
            "Sensitive read was requested while untrusted content is in scope.",
            "medium",
        )

    if mode == "manual" and normalized_tool.startswith(("gmail_", "calendar_", "tasks_", "github_", "drive_")):
        # Only gate connector calls that MODIFY data. Read-only connector reads
        # (gmail_read, gmail_search, calendar_list, calendar_get, read_drive_file, github_read_*,
        # etc.) are allowed without a per-call prompt so a batch of reads in one
        # turn does not spam approvals. Mutating verbs still require approval.
        # (Explicit mutating tools are already caught by _EXTERNAL_SIDE_EFFECT_TOOLS
        # above; this regex covers any other mutating connector action.)
        if _MCP_SIDE_EFFECT_RE.search(normalized_tool):
            return ToolPolicyDecision(
                "require_approval",
                "Manual mode requires approval for connector actions that modify data.",
                "medium",
            )
        return ToolPolicyDecision(
            "allow",
            "Read-only connector call allowed.",
            "low",
        )

    return ToolPolicyDecision("allow", "Allowed by current autonomy policy.", "low")
