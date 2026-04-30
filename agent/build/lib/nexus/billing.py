"""Development-only credit billing helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from nexus.config import settings


@dataclass(frozen=True)
class ModelRate:
    input_per_million_usd: float
    output_per_million_usd: float
    label: str


_FLASH_LITE_RATE = ModelRate(
    input_per_million_usd=0.10,
    output_per_million_usd=0.40,
    label="gemini-3.1-flash-lite-preview",
)
_FLASH_RATE = ModelRate(
    input_per_million_usd=0.30,
    output_per_million_usd=2.50,
    label="gemini-3-flash-preview",
)
_LIVE_RATE = ModelRate(
    input_per_million_usd=3.00,
    output_per_million_usd=12.00,
    label="gemini-live-2.5-flash-native-audio",
)


def _starter_plan() -> dict[str, Any]:
    return {
        "id": settings.default_plan_id,
        "name": settings.default_plan_name,
        "price_usd": settings.default_plan_price_usd,
        "status": "active",
    }


def resolve_rate(source: str, model: str) -> ModelRate:
    normalized_source = (source or "").strip().lower()
    normalized_model = (model or "").strip().lower()

    if normalized_source == "voice.gemini_live":
        return _LIVE_RATE
    if "flash-lite" in normalized_model or "flash_lite" in normalized_model:
        return _FLASH_LITE_RATE
    if "flash" in normalized_model:
        return _FLASH_RATE
    return _FLASH_LITE_RATE


def calculate_usage_credits(
    *,
    source: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
) -> int:
    """Convert model usage to dev-plan credits using coarse nominal pricing."""
    clean_input = max(int(input_tokens or 0), 0)
    clean_output = max(int(output_tokens or 0), 0)
    clean_total = max(int(total_tokens or 0), 0)
    if clean_input == 0 and clean_output == 0 and clean_total == 0:
        return 0

    if clean_input == 0 and clean_output == 0 and clean_total > 0:
        clean_input = clean_total

    rate = resolve_rate(source, model)
    cost_usd = (
        (clean_input / 1_000_000) * rate.input_per_million_usd
        + (clean_output / 1_000_000) * rate.output_per_million_usd
    )
    if cost_usd <= 0:
        return 0
    return max(1, math.ceil(cost_usd / settings.default_credit_unit_usd))


def calculate_screenshot_credits(analysis_mode: str | None) -> int:
    mode = (analysis_mode or "").strip().lower()
    if mode == "vision_full":
        return 2
    return 0


def _coerce_non_negative_int(value: Any, default: int) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return max(int(default), 0)


def build_quota_payload(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    plan = _starter_plan()
    credit_limit = _coerce_non_negative_int(
        data.get("creditLimit", settings.default_credit_limit),
        settings.default_credit_limit,
    )
    credit_used = _coerce_non_negative_int(data.get("creditUsage", 0), 0)
    token_limit = _coerce_non_negative_int(
        data.get("tokenLimit", settings.default_token_limit),
        settings.default_token_limit,
    )
    token_used = _coerce_non_negative_int(data.get("tokenUsage", 0), 0)

    remaining = max(0, credit_limit - credit_used)
    unit = "credits"
    return {
        "plan": plan,
        "credits": {
            "limit": credit_limit,
            "used": credit_used,
            "remaining": remaining,
            "unit": unit,
            "unit_usd": settings.default_credit_unit_usd,
        },
        "tokens": {
            "used": token_used,
            "safety_limit": token_limit,
        },
        "limit": credit_limit,
        "used": credit_used,
        "remaining": remaining,
        "unit": unit,
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "price_usd": plan["price_usd"],
    }
