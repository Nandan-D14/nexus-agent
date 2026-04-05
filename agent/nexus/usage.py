"""Token usage helpers shared across agent and voice integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from nexus.config import settings
from nexus.runtime_config import SessionRuntimeConfig

INPUT_TOKEN_KEYS = (
    "prompt_token_count",
    "prompt_tokens",
    "input_token_count",
    "input_tokens",
)
OUTPUT_TOKEN_KEYS = (
    "candidates_token_count",
    "candidate_token_count",
    "completion_tokens",
    "output_token_count",
    "output_tokens",
)
TOTAL_TOKEN_KEYS = ("total_token_count", "total_tokens")
MODEL_KEYS = ("model_name", "model", "model_id", "response_model")


@dataclass(frozen=True)
class TokenUsageRecord:
    source: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


def get_agent_usage_source(
    runtime_config: SessionRuntimeConfig | None = None,
) -> tuple[str, str]:
    if runtime_config is not None:
        return "agent.gemini", runtime_config.gemini_agent_model

    return "agent.gemini", settings.gemini_agent_model


def get_expected_usage_sources() -> list[str]:
    sources = [get_agent_usage_source()[0]]
    if settings.require_byok or settings.google_api_key or settings.google_project_id:
        sources.append("voice.gemini_live")
    return sources


def extract_token_usage_records(
    value: Any,
    *,
    default_source: str,
    default_model: str = "",
    max_depth: int = 4,
) -> list[TokenUsageRecord]:
    records: list[TokenUsageRecord] = []
    seen_objects: set[int] = set()
    seen_records: set[tuple[str, str, int, int, int]] = set()

    def visit(node: Any, depth: int) -> None:
        if node is None or depth > max_depth:
            return

        if isinstance(node, (str, bytes, int, float, bool)):
            return

        if isinstance(node, Mapping):
            _consume_mapping(node)
            for child in node.values():
                visit(child, depth + 1)
            return

        if isinstance(node, (list, tuple, set, frozenset)):
            for child in node:
                visit(child, depth + 1)
            return

        node_id = id(node)
        if node_id in seen_objects:
            return
        seen_objects.add(node_id)

        mapping = _coerce_mapping(node)
        if mapping is not None:
            _consume_mapping(mapping)
            for child in mapping.values():
                visit(child, depth + 1)
            return

        if hasattr(node, "__dict__"):
            for child in vars(node).values():
                visit(child, depth + 1)

    def _consume_mapping(mapping: Mapping[str, Any]) -> None:
        record = _record_from_mapping(
            mapping,
            default_source=default_source,
            default_model=default_model,
        )
        if record is None:
            return

        fingerprint = (
            record.source,
            record.model,
            record.input_tokens,
            record.output_tokens,
            record.total_tokens,
        )
        if fingerprint in seen_records:
            return
        seen_records.add(fingerprint)
        records.append(record)

    visit(value, 0)
    return records


def _coerce_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "items"):
        try:
            return dict(value.items())
        except Exception:
            return None
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, Mapping):
                return dumped
        except Exception:
            return None
    if hasattr(value, "to_dict"):
        try:
            dumped = value.to_dict()
            if isinstance(dumped, Mapping):
                return dumped
        except Exception:
            return None
    return None


def _record_from_mapping(
    mapping: Mapping[str, Any],
    *,
    default_source: str,
    default_model: str,
) -> TokenUsageRecord | None:
    input_tokens = _first_int(mapping, INPUT_TOKEN_KEYS)
    output_tokens = _first_int(mapping, OUTPUT_TOKEN_KEYS)
    total_tokens = _first_int(mapping, TOTAL_TOKEN_KEYS)

    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    input_value = max(input_tokens or 0, 0)
    output_value = max(output_tokens or 0, 0)
    total_value = max(total_tokens or 0, 0)

    if total_value == 0 and input_value == 0 and output_value == 0:
        return None

    source = _first_text(mapping, ("source",)) or default_source
    model = _first_text(mapping, MODEL_KEYS) or default_model

    return TokenUsageRecord(
        source=source,
        model=model,
        input_tokens=input_value,
        output_tokens=output_value,
        total_tokens=total_value,
    )


def _first_int(mapping: Mapping[str, Any], keys: Iterable[str]) -> int | None:
    for key in keys:
        raw = mapping.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _first_text(mapping: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        raw = mapping.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None
