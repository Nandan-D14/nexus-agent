# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Enforced per-run runtime, tool-call, and credit budgets."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Mapping

from nexus.config import settings


def _non_negative_int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


@dataclass
class TaskBudgetGuard:
    max_runtime_seconds: int
    max_tool_calls: int
    max_credits: int
    tool_calls_used: int = 0
    credits_used: int = 0
    elapsed_before_seconds: float = 0.0
    exhausted_reason: str = ""
    exhausted_code: str = ""

    def __post_init__(self) -> None:
        self._started_monotonic = time.monotonic()

    @classmethod
    def from_budget(
        cls,
        budget: Mapping[str, Any] | None,
        *,
        checkpoint: Mapping[str, Any] | None = None,
    ) -> "TaskBudgetGuard":
        values = dict(budget or {})
        saved = dict(checkpoint or {})
        minutes = _non_negative_int(
            values.get("maxRuntimeMinutes"),
            settings.default_task_max_runtime_minutes,
        )
        return cls(
            max_runtime_seconds=minutes * 60,
            max_tool_calls=_non_negative_int(
                values.get("maxToolCalls"),
                settings.default_task_max_tool_calls,
            ),
            max_credits=_non_negative_int(
                values.get("credits"),
                settings.default_task_budget_credits,
            ),
            tool_calls_used=_non_negative_int(saved.get("tool_calls_used"), 0),
            credits_used=_non_negative_int(saved.get("credits_used"), 0),
            elapsed_before_seconds=max(
                0.0, float(saved.get("elapsed_seconds") or 0.0)
            ),
        )

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_before_seconds + max(
            0.0, time.monotonic() - self._started_monotonic
        )

    @property
    def remaining_runtime_seconds(self) -> float:
        return max(0.0, self.max_runtime_seconds - self.elapsed_seconds)

    @property
    def exhausted(self) -> bool:
        if self.exhausted_code:
            return True
        return self.check_runtime()

    def check_runtime(self) -> bool:
        if self.max_runtime_seconds <= 0 or self.elapsed_seconds >= self.max_runtime_seconds:
            self._exhaust(
                "BUDGET_RUNTIME_EXHAUSTED",
                "The durable run reached its maximum runtime.",
            )
            return True
        return False

    def exhaust_runtime(self) -> None:
        self._exhaust(
            "BUDGET_RUNTIME_EXHAUSTED",
            "The durable run reached its maximum runtime.",
        )

    def before_tool_call(self, tool_name: str) -> bool:
        if self.check_runtime():
            return False
        if self.tool_calls_used >= self.max_tool_calls:
            self._exhaust(
                "BUDGET_TOOL_CALLS_EXHAUSTED",
                f"The durable run reached its {self.max_tool_calls} tool-call limit.",
            )
            return False
        self.tool_calls_used += 1
        return True

    def consume_credits(self, credits: int) -> bool:
        self.credits_used += max(0, int(credits or 0))
        if self.credits_used > self.max_credits:
            self._exhaust(
                "BUDGET_CREDITS_EXHAUSTED",
                f"The durable run exceeded its {self.max_credits}-credit budget.",
            )
            return False
        return True

    def _exhaust(self, code: str, reason: str) -> None:
        if not self.exhausted_code:
            self.exhausted_code = code
            self.exhausted_reason = reason

    def checkpoint(self) -> dict[str, Any]:
        return {
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_tool_calls": self.max_tool_calls,
            "max_credits": self.max_credits,
            "tool_calls_used": self.tool_calls_used,
            "credits_used": self.credits_used,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "exhausted_code": self.exhausted_code,
            "exhausted_reason": self.exhausted_reason,
        }


__all__ = ["TaskBudgetGuard"]
