# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Provider-neutral screenshot grounding backed by Qwen vision."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
import json
import logging
import re
from typing import Any, Protocol

from openai import AsyncOpenAI, OpenAI

from nexus.config import settings
from nexus.resilience import retry_sync


logger = logging.getLogger(__name__)


class VisionAnalysisError(RuntimeError):
    """Raised when every configured Qwen vision tier fails."""


class QwenCapabilityError(RuntimeError):
    """Raised when required Qwen text/tool or multimodal capability is absent."""


@dataclass(frozen=True)
class VisionTarget:
    label: str
    x: int | None = None
    y: int | None = None
    selector: str = ""
    kind: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class ScreenObservation:
    visible_state: str
    focus: str = ""
    targets: tuple[VisionTarget, ...] = ()
    visible_text: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    next_action: str = ""
    confidence: float = 0.0
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_description(self, limit: int = 1_200) -> str:
        lines = [
            f"STATE: {self.visible_state or 'Screen captured.'}",
            f"FOCUS: {self.focus or 'No focused element identified.'}",
            "ELEMENTS:",
        ]
        for target in self.targets[:10]:
            coordinate = (
                f" @ ({target.x}, {target.y})"
                if target.x is not None and target.y is not None
                else ""
            )
            selector = f" selector={target.selector}" if target.selector else ""
            lines.append(
                f"- {target.label}{coordinate}{selector} confidence={target.confidence:.2f}"
            )
        if not self.targets:
            lines.append("- No reliable target identified.")
        lines.append("TEXT:")
        lines.extend(f"- {text}" for text in self.visible_text[:8])
        if self.errors:
            lines.append("ERRORS:")
            lines.extend(f"- {error}" for error in self.errors[:5])
        lines.append(f"NEXT_ACTION: {self.next_action or 'Observe or use DOM inspection.'}")
        text = "\n".join(lines)
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class VisionProvider(Protocol):
    def analyze(
        self,
        image_bytes: bytes,
        *,
        width: int,
        height: int,
        task_context: str = "",
    ) -> ScreenObservation:
        ...


def _parse_models(primary: str, fallbacks: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for model in (primary, *fallbacks):
        model = str(model).strip()
        if not model or model in ordered:
            continue
        if not model.lower().startswith("qwen"):
            raise ValueError(f"Qwen vision rejected non-Qwen model: {model}")
        ordered.append(model)
    return tuple(ordered)


def _json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise VisionAnalysisError("Qwen vision did not return a JSON object")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise VisionAnalysisError("Qwen vision response must be a JSON object")
    return value


def _bounded_coordinate(value: Any, maximum: int) -> int | None:
    try:
        return max(0, min(int(round(float(value))), maximum))
    except (TypeError, ValueError):
        return None


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _observation_from_payload(
    payload: dict[str, Any],
    *,
    width: int,
    height: int,
    model: str,
) -> ScreenObservation:
    targets: list[VisionTarget] = []
    for raw in payload.get("targets", ())[:20]:
        if not isinstance(raw, dict):
            continue
        coordinates = raw.get("coordinates")
        if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
            raw_x, raw_y = coordinates[0], coordinates[1]
        elif isinstance(coordinates, dict):
            raw_x, raw_y = coordinates.get("x"), coordinates.get("y")
        else:
            raw_x, raw_y = raw.get("x"), raw.get("y")
        label = str(raw.get("label") or raw.get("text") or "").strip()
        if not label:
            continue
        targets.append(
            VisionTarget(
                label=label[:200],
                x=_bounded_coordinate(raw_x, width),
                y=_bounded_coordinate(raw_y, height),
                selector=str(raw.get("selector") or "")[:500],
                kind=str(raw.get("kind") or raw.get("type") or "")[:80],
                confidence=_confidence(raw.get("confidence")),
            )
        )
    return ScreenObservation(
        visible_state=str(
            payload.get("visible_state") or payload.get("state") or "Screen captured."
        )[:800],
        focus=str(payload.get("focus") or "")[:500],
        targets=tuple(targets),
        visible_text=tuple(
            str(item)[:300]
            for item in payload.get("visible_text", payload.get("text", ()))[:20]
            if str(item).strip()
        ),
        errors=tuple(
            str(item)[:300]
            for item in payload.get("errors", ())[:10]
            if str(item).strip()
        ),
        next_action=str(payload.get("next_action") or "")[:500],
        confidence=_confidence(payload.get("confidence")),
        model=model,
    )


class QwenVisionProvider:
    def __init__(
        self,
        *,
        api_key: str,
        api_base: str,
        primary_model: str,
        fallback_models: tuple[str, ...] = (),
        timeout_seconds: float = 60.0,
        attempts_per_model: int = 1,
        retry_base_seconds: float = 1.0,
    ) -> None:
        if not api_key.strip():
            raise VisionAnalysisError("QWEN_API_KEY is required for screenshot analysis")
        self._client = OpenAI(
            api_key=api_key,
            base_url=api_base.rstrip("/"),
            timeout=timeout_seconds,
        )
        self.models = _parse_models(primary_model, fallback_models)
        self._attempts_per_model = max(1, int(attempts_per_model))
        self._retry_base_seconds = max(0.0, float(retry_base_seconds))

    def analyze(
        self,
        image_bytes: bytes,
        *,
        width: int,
        height: int,
        task_context: str = "",
    ) -> ScreenObservation:
        image_url = (
            "data:image/jpeg;base64,"
            + base64.b64encode(image_bytes).decode("ascii")
        )
        prompt = (
            "Ground this desktop screenshot for an autonomous computer agent. "
            f"Image coordinates use width={width}, height={height}, origin top-left. "
            "Return JSON only with keys: visible_state (string), focus (string), "
            "targets (array of {label, kind, coordinates:[x,y], selector, confidence}), "
            "visible_text (array of strings), errors (array of strings), "
            "next_action (string), confidence (0..1). "
            "Never infer hidden controls. Coordinates must be inside the image. "
            f"Current task context: {task_context[:500] or 'not provided'}"
        )
        errors: list[str] = []
        for index, model in enumerate(self.models):
            if index > 0:
                previous = self.models[index - 1]
                reason = errors[-1] if errors else f"{previous} failed"
                _emit_vision_model_fallback(
                    from_model=previous,
                    to_model=model,
                    reason=reason,
                )
            def _ground() -> ScreenObservation:
                response = self._client.chat.completions.create(
                    model=model,
                    temperature=0,
                    max_tokens=1_200,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                )
                text = response.choices[0].message.content or ""
                return _observation_from_payload(
                    _json_object(text),
                    width=width,
                    height=height,
                    model=model,
                )

            try:
                return retry_sync(
                    _ground,
                    attempts=self._attempts_per_model,
                    base_delay=self._retry_base_seconds,
                    label=f"qwen vision grounding ({model})",
                )
            except Exception as exc:
                errors.append(f"{model}: {type(exc).__name__}: {str(exc)[:240]}")
                logger.warning(
                    "Qwen vision model %s failed after %d attempt(s)",
                    model,
                    self._attempts_per_model,
                    exc_info=True,
                )
        raise VisionAnalysisError(
            "All Qwen vision models failed: " + " | ".join(errors)
        )


def _emit_vision_model_fallback(
    *,
    from_model: str,
    to_model: str,
    reason: str,
) -> None:
    """Emit a correlated fallback event before changing Qwen vision tiers."""
    from nexus.event_sink import prepare_correlated_event
    from nexus.tracing import get_trace_context

    payload: dict[str, Any] = {
        "type": "agent_model_fallback",
        "role": "vision",
        "from_model": from_model,
        "to_model": to_model,
        "reason": reason[:500],
        "provider": "qwen",
    }
    try:
        payload = prepare_correlated_event(payload, get_trace_context())
    except Exception:
        logger.debug("Unable to correlate vision fallback event", exc_info=True)
    try:
        from nexus.tools._context import get_send_json

        send_json = get_send_json()
        if send_json is not None:
            result = send_json(payload)
            if hasattr(result, "__await__"):
                # Best-effort: sync vision path cannot await; schedule if loop exists.
                try:
                    import asyncio

                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    logger.info(
                        "vision_model_fallback from=%s to=%s reason=%s",
                        from_model,
                        to_model,
                        reason[:240],
                    )
            return
    except Exception:
        logger.debug("Unable to emit vision fallback event", exc_info=True)
    logger.info(
        "vision_model_fallback from=%s to=%s reason=%s",
        from_model,
        to_model,
        reason[:240],
    )


def create_vision_provider(
    *,
    primary_model: str | None = None,
    fallback_models: tuple[str, ...] | None = None,
) -> QwenVisionProvider:
    return QwenVisionProvider(
        api_key=settings.qwen_api_key,
        api_base=settings.qwen_api_base,
        primary_model=primary_model or settings.qwen_vision_model,
        fallback_models=(
            fallback_models
            if fallback_models is not None
            else tuple(
                model.strip()
                for model in settings.qwen_vision_fallback_models.split(",")
                if model.strip()
            )
        ),
        timeout_seconds=settings.vision_request_timeout_seconds,
        attempts_per_model=settings.vision_attempts_per_model,
        retry_base_seconds=settings.vision_retry_base_seconds,
    )


@dataclass(frozen=True)
class QwenCapabilityReport:
    text_tool_calling: bool
    vision: bool
    text_model: str
    vision_model: str


async def probe_qwen_capabilities() -> QwenCapabilityReport:
    """Probe required production capabilities without forcing tool_choice."""

    if not settings.qwen_api_key.strip():
        raise QwenCapabilityError("QWEN_API_KEY is not configured")
    client = AsyncOpenAI(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_api_base.rstrip("/"),
        timeout=30.0,
    )
    try:
        text_response = await client.chat.completions.create(
            model=settings.planner_model,
            messages=[
                {
                    "role": "user",
                    "content": "Call capability_probe with value qwen_tool_ok. Do not answer in prose.",
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "capability_probe",
                        "description": "Return a capability probe value.",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        },
                    },
                }
            ],
            tool_choice="auto",
            max_tokens=128,
        )
        text_tool_calling = bool(text_response.choices[0].message.tool_calls)
    except Exception as exc:
        raise QwenCapabilityError(
            f"Qwen text/tool capability probe failed: {type(exc).__name__}: {str(exc)[:300]}"
        ) from exc
    if not text_tool_calling:
        raise QwenCapabilityError(
            f"Qwen model {settings.planner_model} did not produce a tool call"
        )

    one_pixel_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/x8AAusB9Y9Z4VQAAAAASUVORK5CYII="
    )
    try:
        vision_response = await client.chat.completions.create(
            model=settings.qwen_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Reply with VISION_OK if you can inspect this image."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{one_pixel_png}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=32,
        )
        vision_ok = "VISION_OK" in (
            vision_response.choices[0].message.content or ""
        ).upper()
    except Exception as exc:
        raise QwenCapabilityError(
            f"Qwen vision capability probe failed: {type(exc).__name__}: {str(exc)[:300]}"
        ) from exc
    if not vision_ok:
        raise QwenCapabilityError(
            f"Qwen model {settings.qwen_vision_model} did not confirm multimodal input"
        )
    return QwenCapabilityReport(
        text_tool_calling=True,
        vision=True,
        text_model=settings.planner_model,
        vision_model=settings.qwen_vision_model,
    )


__all__ = [
    "QwenCapabilityError",
    "QwenCapabilityReport",
    "QwenVisionProvider",
    "ScreenObservation",
    "VisionAnalysisError",
    "VisionProvider",
    "VisionTarget",
    "create_vision_provider",
    "probe_qwen_capabilities",
]
