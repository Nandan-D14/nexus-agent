# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""triple_click support: sandbox input primitive + tool export."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.sandbox_components.input import SandboxInput


class _FakeSandbox:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def left_click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class _FakeOwner:
    def __init__(self, sandbox: _FakeSandbox) -> None:
        self._sandbox = sandbox
        self._stream_url = None
        self._e2b_api_key = "test-key"

    def _require_sandbox(self) -> None:
        if self._sandbox is None:
            raise RuntimeError("no sandbox")


def test_triple_click_issues_three_left_clicks() -> None:
    fake = _FakeSandbox()
    component = SandboxInput(_FakeOwner(fake))

    component.triple_click(120, 240)

    assert fake.clicks == [(120, 240), (120, 240), (120, 240)]


def test_triple_click_tool_is_exported() -> None:
    from nexus.tools import triple_click

    assert callable(triple_click)
