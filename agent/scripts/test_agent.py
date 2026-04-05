"""Quick test: run the ADK agent with a text command (no voice)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nexus.agent import create_agent, create_runner, run_agent_turn
from nexus.sandbox import SandboxManager
from nexus.tools._context import set_sandbox


async def main():
    print("=== co-computer Agent Test (text mode) ===\n")

    # Boot sandbox
    print("[1/3] Creating sandbox...")
    sandbox = SandboxManager()
    sandbox.create()
    set_sandbox(sandbox)
    print(f"  Stream URL: {sandbox.stream_url}\n")

    # Create agent
    print("[2/3] Creating ADK agent...")
    agent = create_agent()
    runner, session_service = create_runner(agent)
    print("  Agent ready.\n")

    # Run a task
    task = input("Enter a task (or press Enter for default): ").strip()
    if not task:
        task = "Take a screenshot and describe what you see on the screen."

    print(f"\n[3/3] Running agent with: '{task}'\n")

    async def on_event(event):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  [Agent] {part.text[:200]}")
        if hasattr(event, "actions") and event.actions:
            print(f"  [Action] {event.actions}")

    response = await run_agent_turn(
        runner=runner,
        session_service=session_service,
        session_id="test-session",
        user_id="test-user",
        message=task,
        event_callback=on_event,
    )

    print(f"\n=== Final response ===\n{response}\n")

    # Cleanup
    sandbox.destroy()
    print("Sandbox destroyed. Test complete.")


if __name__ == "__main__":
    asyncio.run(main())
