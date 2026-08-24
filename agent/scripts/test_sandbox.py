# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Standalone test: boot an E2B sandbox, print stream URL, take screenshot, destroy."""

import sys
import time
from pathlib import Path

# Allow running from agent/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from nexus.sandbox import SandboxManager


def main():
    manager = SandboxManager()

    print("Booting E2B desktop sandbox...")
    stream_url = manager.create()
    print(f"  Stream URL : {stream_url}")
    print()
    print("Open the stream URL in a browser to see the live Linux desktop.")
    print("Waiting 5 seconds then taking a screenshot...")

    time.sleep(5)

    png_bytes = manager.screenshot()
    out_path = Path("test_screenshot.png")
    out_path.write_bytes(png_bytes)
    print(f"Screenshot saved to {out_path.resolve()} ({len(png_bytes)} bytes)")

    # Run a quick command
    print("\nRunning 'uname -a' in sandbox...")
    stdout, stderr, exit_code = manager.run_command("uname -a")
    print(f"  stdout: {stdout.strip()}")
    print(f"  exit_code: {exit_code}")

    print("\nDestroying sandbox...")
    manager.destroy()
    print("Done.")


if __name__ == "__main__":
    main()
