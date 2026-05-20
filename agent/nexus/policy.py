# Copyright (c) 2026 Agentic Company. All rights reserved.
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
    "tasks_create",
    "github_create_issue",
    "upload_drive_file",
    "create_drive_doc",
}

_SENSITIVE_READ_TOOLS = {
    "gmail_read",
    "read_drive_file",
    "github_read_file",
}

_DESTRUCTIVE_COMMAND_RE = re.compile(
    r"(?is)(\brm\s+-[^;\n]*[rf]|"
    r"\bRemove-Item\b[^;\n]*(?:-Recurse|-Force)|"
    r"\brmdir\b[^;\n]*(?:/s|-r)|"
    r"\bdel\b[^;\n]*(?:/s|/q)|"
    r"\bsudo\b|"
    r"\bmkfs\b|"
    r"\bdd\s+if=|"
    r"\bshutdown\b|"
    r"\breboot\b|"
    r"\bkillall\b|"
    r"\bchmod\s+-R\s+777\b|"
    r"\bgit\s+reset\s+--hard\b|"
    r"\bgit\s+clean\s+-[^;\n]*[fd]|"
    r"\bdrop\s+(?:database|schema|table)\b|"
    r"\btruncate\s+table\b|"
    r"\bvercel\b[^;\n]*--prod\b|"
    r"\bfirebase\s+deploy\b|"
    r"\bcurl\b[^;\n|]*\|\s*(?:sh|bash)|"
    r"\bwget\b[^;\n|]*\|\s*(?:sh|bash))"
)

_SECRET_EXFIL_RE = re.compile(
    r"(?is)(GOOGLE_APPLICATION_CREDENTIALS|"
    r"googleDriveRefreshToken|"
    r"refresh_token|"
    r"api[_-]?key|"
    r"authorization|"
    r"bearer\s+[A-Za-z0-9._-]+|"
    r"\.config/rclone|"
    r"userPrivate)"
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
) -> ToolPolicyDecision:
    """Return the policy decision for a tool call before execution.

    Manual mode still allows low-risk local work. Auto Mode removes approval for
    medium-risk actions, but high-impact external/destructive actions remain gated.
    """
    normalized_tool = (tool_name or "").strip()
    mode = normalize_autonomy_mode(autonomy_mode)
    args = args or {}

    if normalized_tool == "run_command":
        command = str(args.get("command") or "")
        if _SECRET_EXFIL_RE.search(command):
            return ToolPolicyDecision(
                "deny",
                "Command appears to read or expose credentials/secrets.",
                "blocked",
            )
        if _DESTRUCTIVE_COMMAND_RE.search(command):
            return ToolPolicyDecision(
                "require_approval",
                "Command can modify or destroy system state.",
                "high",
            )
        return ToolPolicyDecision("allow", "Low-risk shell command.", "medium")

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
        return ToolPolicyDecision(
            "require_approval",
            "Manual mode requires approval for connector actions.",
            "medium",
        )

    return ToolPolicyDecision("allow", "Allowed by current autonomy policy.", "low")
