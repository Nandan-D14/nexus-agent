# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Turn context builder (production stack Layer 1).

One place that decides what goes into the model's turn input and in what
order, under an explicit character budget. The orchestrator produces the
individual blocks (seed context, resume packet, memory facts, connector and
upload context); this module owns prioritization and truncation so context
assembly stops being scattered ad-hoc string concatenation.

Priorities (lower number = dropped last):
  10  seed / resume context  — task continuity, most load-bearing
  20  turn context           — connectors and uploaded files for THIS turn
  30  user memory            — nice to have, first to shrink
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from nexus.config import settings

logger = logging.getLogger(__name__)

PRIORITY_RESUME = 10
PRIORITY_TURN = 20
PRIORITY_MEMORY = 30


@dataclass(frozen=True)
class ContextBlock:
    label: str
    text: str
    priority: int


@dataclass
class BuiltTurnInput:
    text: str
    included_labels: list[str] = field(default_factory=list)
    dropped_labels: list[str] = field(default_factory=list)


class TurnContextBuilder:
    """Collects context blocks and assembles the final turn input."""

    def __init__(self, *, max_chars: int | None = None) -> None:
        self._blocks: list[ContextBlock] = []
        self._max_chars = max_chars or settings.turn_context_max_chars

    def add(self, label: str, text: str, *, priority: int = PRIORITY_TURN) -> None:
        cleaned = (text or "").strip()
        if cleaned:
            self._blocks.append(ContextBlock(label=label, text=cleaned, priority=priority))

    def build(self, user_text: str) -> BuiltTurnInput:
        """Assemble blocks + user text under the character budget.

        The user's message is always included in full. Blocks are added in
        insertion order; when the budget would be exceeded, the lowest-priority
        (highest number) blocks are dropped first, whole-block, so the model
        never sees a mid-sentence cut.
        """
        user = (user_text or "").strip()
        budget = self._max_chars - len(user) - len("\n\nUser: ")
        if budget < 0:
            budget = 0

        # Decide inclusion by priority, then emit in insertion order.
        by_priority = sorted(
            enumerate(self._blocks), key=lambda item: (item[1].priority, item[0])
        )
        included_indices: set[int] = set()
        used = 0
        dropped: list[str] = []
        for index, block in by_priority:
            cost = len(block.text) + 2
            if used + cost <= budget:
                included_indices.add(index)
                used += cost
            else:
                dropped.append(block.label)

        parts = [
            block.text
            for index, block in enumerate(self._blocks)
            if index in included_indices
        ]
        included = [
            block.label
            for index, block in enumerate(self._blocks)
            if index in included_indices
        ]
        if dropped:
            logger.info(
                "TurnContextBuilder dropped %d block(s) over budget: %s",
                len(dropped),
                ", ".join(dropped),
            )

        if parts:
            joined = "\n\n".join(parts)
            text = f"{joined}\n\nUser: {user}" if user else joined
        else:
            text = user
        return BuiltTurnInput(text=text, included_labels=included, dropped_labels=dropped)
