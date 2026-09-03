# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Sandbox git helpers authenticated with the user's connected GitHub token.

The token is written to a 0600 file and a credential helper. Git commands use
https://github.com/... URLs with no embedded secret, and command output is
scrubbed before it returns to the model.
"""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import Any

GH_CC_DIR = "/home/user/.config/gh-cc"
TOKEN_PATH = f"{GH_CC_DIR}/token"
HELPER_PATH = f"{GH_CC_DIR}/credential-helper.sh"

_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

_HELPER_SCRIPT = """#!/bin/sh
if [ "$1" = get ]; then
  echo "username=x-access-token"
  echo "password=$(cat /home/user/.config/gh-cc/token)"
fi
"""


def scrub_secret(text: str, token: str) -> str:
    if not text or not token:
        return text or ""
    return text.replace(token, "***")


def validate_github_name(value: str, *, kind: str) -> str | None:
    name = (value or "").strip()
    if not name or name in {".", ".."} or not _GITHUB_NAME_RE.fullmatch(name):
        return f"Invalid GitHub {kind}."
    return None


def resolve_workspace_path(workspace: str, dest: str, *, default_name: str = "") -> str:
    """Resolve dest to an absolute path that stays inside the workspace."""
    root = (workspace or "").rstrip("/") or "/home/user/CoComputer/Workspaces"
    raw = (dest or "").strip().replace("\\", "/")
    if not raw:
        if not default_name:
            return root
        raw = default_name
    if raw.startswith("/"):
        candidate = PurePosixPath(raw)
    else:
        candidate = PurePosixPath(root) / raw
    resolved = PurePosixPath(*[part for part in candidate.parts if part not in ("", ".")])
    root_path = PurePosixPath(root)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("Path must stay inside the active workspace.") from exc
    if ".." in resolved.parts:
        raise ValueError("Path must stay inside the active workspace.")
    return str(resolved)


def install_github_git_credentials(sandbox: Any, token: str) -> None:
    """Install a GitHub credential helper in the sandbox. Never logs the token."""
    if not token:
        raise ValueError("GitHub token is required.")
    sandbox.ensure_directory(GH_CC_DIR)
    sandbox.write_binary_file(TOKEN_PATH, token.encode("utf-8"))
    sandbox.write_text_file(HELPER_PATH, _HELPER_SCRIPT)
    sandbox.run_command(
        "chmod 600 {token} && chmod 700 {helper} && "
        "git config --global credential.https://github.com.helper {helper} && "
        "git config --global credential.https://github.com.useHttpPath true".format(
            token=shlex.quote(TOKEN_PATH),
            helper=shlex.quote(HELPER_PATH),
        ),
        timeout=30,
    )


def configure_git_identity(sandbox: Any, name: str, email: str) -> None:
    safe_name = (name or "CoComputer").strip() or "CoComputer"
    safe_email = (email or "noreply@users.noreply.github.com").strip()
    sandbox.run_command(
        "git config --global user.name {name} && git config --global user.email {email}".format(
            name=shlex.quote(safe_name),
            email=shlex.quote(safe_email),
        ),
        timeout=15,
    )


def run_sandbox_git(
    sandbox: Any,
    argv: list[str],
    *,
    token: str,
    timeout: int = 120,
) -> dict[str, Any]:
    """Run a git command. ``argv`` must start with ``git`` and must not include the token."""
    if not argv or argv[0] != "git":
        raise ValueError("git argv must start with git")
    command = "GIT_TERMINAL_PROMPT=0 " + " ".join(shlex.quote(part) for part in argv)
    result = sandbox.run_command(command, timeout=timeout) or {}
    return {
        "stdout": scrub_secret(str(result.get("stdout") or ""), token),
        "stderr": scrub_secret(str(result.get("stderr") or ""), token),
        "exit_code": result.get("exit_code", -1),
        "command": command,
    }
