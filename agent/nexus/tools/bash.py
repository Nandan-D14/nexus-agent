"""Terminal command execution tool."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_command(command: str, background: bool = False) -> dict:
    """Run a shell command in the Linux terminal and return the output.

    Use this to execute any bash command: file operations, package installs,
    running scripts, git commands, system commands, etc.

    For GUI applications (like file managers, browsers, text editors) that
    stay open, set background=True so the command doesn't block.

    Args:
        command: The bash command to execute.
        background: If True, launch the command in the background. Use for
            GUI apps or long-running processes that don't exit immediately.

    Returns:
        dict with stdout, stderr, and exit_code.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        result = sandbox.run_command(command, timeout=120, background=background)
        return result
    except Exception as e:
        logger.error("run_command failed: %s", e)
        return {"status": "error", "message": f"Command failed: {e}", "stdout": "", "stderr": str(e), "exit_code": -1}
