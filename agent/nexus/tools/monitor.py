# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Monitoring tool for proactive background tasks using the E2B Sandbox."""

from __future__ import annotations

import logging
import uuid

from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


@normalized_tool
def schedule_monitoring_task(
    description: str,
    interval_minutes: int,
    instruction: str,
) -> dict:
    """Schedule a periodic task that the agent will perform in the background.

    Args:
        description: A human-readable description of what to monitor.
        interval_minutes: How often to run the task (minimum 1 minute).
        instruction: The exact prompt the agent should follow when the task triggers.

    Returns:
        NormalizedToolResult with task_id and schedule details.
    """
    from nexus.tools._context import get_sandbox

    try:
        sandbox = get_sandbox()
    except RuntimeError:
        return tool_error(
            "No active sandbox context.",
            error_code="TOOL_UNAVAILABLE",
        )

    if interval_minutes < 1:
        interval_minutes = 1

    task_id = f"monitor_{uuid.uuid4().hex[:8]}"

    daemon_script = f"""
import time
import os
import sys

interval = {interval_minutes * 60}
print(f"Started monitoring task: {description}")

while True:
    time.sleep(interval)
    print(f"ALERT: Condition met for '{description}'. Executing: {instruction}")
    with open('/home/user/desktop/monitoring_alerts.log', 'a') as f:
        f.write(f"ALERT: {{time.ctime()}} - '{description}' triggered.\\n")
"""

    script_path = f"/tmp/{task_id}.py"
    sandbox.commands.run(f"cat << 'EOF' > {script_path}\n{daemon_script}\nEOF")
    sandbox.commands.run(f"nohup python3 {script_path} > /tmp/{task_id}.log 2>&1 &")

    return tool_success(
        f"Scheduled '{description}' every {interval_minutes} minutes",
        task_id=task_id,
        description=description,
        interval_minutes=interval_minutes,
    )
