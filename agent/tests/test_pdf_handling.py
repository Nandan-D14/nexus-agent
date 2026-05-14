# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools.bash import run_command


def test_run_command_refuses_pdf_base64_dump() -> None:
    result = run_command("cat /home/user/pdf_base64.txt")

    assert result["status"] == "success"
    assert "Skipped PDF/base64 dump" in result["summary"]


def test_run_command_refuses_pdf_dump() -> None:
    result = run_command("cat /home/user/uploads/file.pdf")

    assert result["status"] == "success"
    assert "Skipped PDF/base64 dump" in result["summary"]
