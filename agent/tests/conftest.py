# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared test defaults.

The developer .env may enable production features (durable task worker,
memory injection) that reach real Firestore. Tests must opt in explicitly
via monkeypatch instead of inheriting live settings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.config import settings


@pytest.fixture(autouse=True)
def _production_stack_test_defaults(monkeypatch):
    monkeypatch.setattr(settings, "task_worker_enabled", False)
    monkeypatch.setattr(settings, "memory_enabled", False)
