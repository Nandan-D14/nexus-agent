# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Turn-intent routing: deterministic heuristics first, micro model when ambiguous.

The orchestrator must know whether a user message is a confirmation of the
previous task ("continue", "ship it"), a demand for a missing deliverable
("where is my deck"), or an inquiry about the last error. Regexes decide the
clear cases for free. Only a short message that matches none of them while a
substantial task is outstanding — the case regex lists keep missing ("sounds
good, go for it", "yes but in blue") — goes to the micro model, with a short
timeout. Any model failure falls back to the heuristic answer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from google.genai import types

from nexus.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnIntent:
    is_followup: bool = False
    is_deliverable_demand: bool = False
    is_error_inquiry: bool = False
    source: str = "heuristic"


_INTENT_SYSTEM = (
    "Classify the user's latest chat message relative to the task already in "
    "progress. Reply with JSON only: "
    '{"followup": bool, "deliverable_demand": bool, "error_inquiry": bool}. '
    "followup = it confirms, approves, or tweaks the in-progress task rather "
    "than starting a different one. deliverable_demand = it asks where the "
    "promised output is or asks to be given it. error_inquiry = it asks what "
    "went wrong last time."
)
_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def heuristic_intent(text: str) -> TurnIntent:
    from nexus.turn_heuristics import is_deliverable_demand, is_error_inquiry, is_short_followup

    return TurnIntent(
        is_followup=is_short_followup(text),
        is_deliverable_demand=is_deliverable_demand(text),
        is_error_inquiry=is_error_inquiry(text),
    )


def _needs_model(text: str, heuristic: TurnIntent, previous_task: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or not str(previous_task or "").strip():
        return False
    if heuristic.is_followup or heuristic.is_deliverable_demand or heuristic.is_error_inquiry:
        return False
    if stripped.startswith(("/", "[")):
        return False
    return len(stripped) <= int(settings.intent_classifier_max_chars)


async def _model_intent(text: str, previous_task: str, runtime_config: Any) -> TurnIntent | None:
    from google.adk.models.llm_request import LlmRequest

    from nexus.model_select import create_model

    model = create_model("micro", runtime_config)
    prompt = (
        f"TASK IN PROGRESS:\n{previous_task.strip()[:800]}\n\n"
        f"LATEST MESSAGE:\n{text.strip()}"
    )
    request = LlmRequest(
        model=getattr(model, "model", None),
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(system_instruction=_INTENT_SYSTEM, temperature=0.0),
    )
    chunks: list[str] = []
    async for response in model.generate_content_async(request, stream=False):
        content = getattr(response, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None) and not getattr(part, "thought", False):
                chunks.append(part.text)
    match = _JSON_RE.search("".join(chunks))
    if not match:
        return None
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        return None
    return TurnIntent(
        is_followup=bool(data.get("followup")),
        is_deliverable_demand=bool(data.get("deliverable_demand")),
        is_error_inquiry=bool(data.get("error_inquiry")),
        source="model",
    )


async def classify_turn_intent(
    text: str,
    *,
    previous_task: str = "",
    runtime_config: Any = None,
) -> TurnIntent:
    """Return the turn intent; never raises and never blocks past the timeout."""
    heuristic = heuristic_intent(text)
    if not settings.intent_classifier_enabled or not _needs_model(text, heuristic, previous_task):
        return heuristic
    try:
        result = await asyncio.wait_for(
            _model_intent(text, previous_task, runtime_config),
            timeout=float(settings.intent_classifier_timeout_seconds),
        )
    except Exception as exc:
        logger.info("Intent classifier fell back to heuristics: %s", exc)
        return heuristic
    return result or heuristic


__all__ = ["TurnIntent", "classify_turn_intent", "heuristic_intent"]
