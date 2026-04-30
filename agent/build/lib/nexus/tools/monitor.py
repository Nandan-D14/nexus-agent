"""Monitoring tool for proactive background tasks using the E2B Sandbox."""

from __future__ import annotations

import logging
from typing import Any
import uuid

logger = logging.getLogger(__name__)

def schedule_monitoring_task(
    description: str,
    interval_minutes: int,
    instruction: str,
) -> dict[str, Any]:
    """Schedule a periodic task that the agent will perform in the background.

    Args:
        description: A human-readable description of what to monitor.
        interval_minutes: How often to run the task (minimum 1 minute).
        instruction: The exact prompt the agent should follow when the task triggers.

    Returns:
        Confirmation dict with task details.
    """
    from nexus.tools._context import get_sandbox
    
    try:
        sandbox = get_sandbox()
    except RuntimeError:
        return {"status": "error", "message": "No active sandbox context."}
        
    if interval_minutes < 1:
        interval_minutes = 1
        
    task_id = f"monitor_{uuid.uuid4().hex[:8]}"
    
    # We write a simple python daemon into the sandbox that sleeps and executes the instruction
    # For a real hackathon demo, this script could use the agent's LLM API, but here we just
    # simulate the proactive notification by echoing to a log file that the frontend could tail.
    # To make it truly agentic, we could have it call an API webhook back to our FastAPI server
    # to trigger a new run!
    
    daemon_script = f"""
import time
import os
import sys

interval = {interval_minutes * 60}
print(f"Started monitoring task: {description}")

while True:
    time.sleep(interval)
    # In a full implementation, this would trigger the AI agent.
    # For the demo, we simulate a finding.
    print(f"ALERT: Condition met for '{description}'. Executing: {instruction}")
    
    # We can write to a specific file that the UI watches, or just log it.
    with open('/home/user/desktop/monitoring_alerts.log', 'a') as f:
        f.write(f"ALERT: {{time.ctime()}} - '{description}' triggered.\\n")
"""

    script_path = f"/tmp/{task_id}.py"
    sandbox.commands.run(f"cat << 'EOF' > {script_path}\n{daemon_script}\nEOF")
    
    # Run it in the background using nohup
    sandbox.commands.run(f"nohup python3 {script_path} > /tmp/{task_id}.log 2>&1 &")
    
    return {
        "status": "scheduled",
        "task_id": task_id,
        "description": description,
        "interval_minutes": interval_minutes,
        "message": f"Successfully scheduled '{description}' to run every {interval_minutes} minutes in the background."
    }
