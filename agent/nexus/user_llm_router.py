# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Per-session LiteLLM client for user-supplied OpenAI-compatible credentials.

Unlike the Qwen/Bynara/Vultr routers this module never caches a process-wide
client. User API keys must not leak across sessions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from google.adk.models.lite_llm import LiteLlm

from nexus.router_common import (
    apply_request_timeout,
    apply_tool_call_policy,
    repair_tool_call_ids,
)

if TYPE_CHECKING:
    from nexus.runtime_config import SessionRuntimeConfig

logger = logging.getLogger(__name__)


def _strip_openai_prefix(model: str) -> str:
    name = (model or "").strip()
    if name.startswith("openai/"):
        return name[len("openai/") :]
    return name


class UserLlmClient:
    """Delegates completions to LiteLLM with per-session api_key and api_base."""

    def __init__(self, *, api_key: str, api_base: str) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")

    def _call_kwargs(self, model: str, tools: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = apply_request_timeout(apply_tool_call_policy(dict(kwargs), tools))
        normalized["api_key"] = self.api_key
        normalized["api_base"] = self.api_base
        normalized["model"] = f"openai/{_strip_openai_prefix(model)}"
        return normalized

    async def acompletion(self, model, messages, tools, **kwargs):
        import litellm

        call_kwargs = self._call_kwargs(model, tools, kwargs)
        logger.info(
            "Routing request asynchronously to user LLM model: %s",
            _strip_openai_prefix(model),
        )
        response = await litellm.acompletion(
            messages=messages,
            tools=tools,
            **call_kwargs,
        )
        if not call_kwargs.get("stream"):
            repair_tool_call_ids(response)
        return response

    def completion(self, model, messages, tools, stream=False, **kwargs):
        import litellm

        call_kwargs = self._call_kwargs(model, tools, kwargs)
        call_kwargs["stream"] = stream
        logger.info(
            "Routing request synchronously to user LLM model: %s",
            _strip_openai_prefix(model),
        )
        response = litellm.completion(
            messages=messages,
            tools=tools,
            **call_kwargs,
        )
        if not stream:
            repair_tool_call_ids(response)
        return response


def create_user_llm_model(
    model_name: str,
    runtime_config: "SessionRuntimeConfig",
) -> LiteLlm:
    """Create a LiteLlm wrapper bound to the session's user credentials."""
    name = (model_name or "").strip() or runtime_config.llm_model
    if not runtime_config.user_llm_configured:
        raise RuntimeError("User LLM credentials are not configured for this session.")
    if not name:
        raise ValueError("User LLM model id is empty.")
    model = LiteLlm(model=name)
    model.llm_client = UserLlmClient(
        api_key=runtime_config.llm_api_key,
        api_base=runtime_config.llm_api_base,
    )
    return model


async def probe_user_llm(runtime_config: "SessionRuntimeConfig") -> str:
    """Issue a one-token completion to verify the user's key, base URL, and model."""
    from openai import AsyncOpenAI

    if not runtime_config.user_llm_configured:
        raise ValueError("Choose an LLM provider and supply an API key and model first.")
    client = AsyncOpenAI(
        api_key=runtime_config.llm_api_key,
        base_url=runtime_config.llm_api_base.rstrip("/"),
        timeout=20.0,
    )
    try:
        await client.chat.completions.create(
            model=runtime_config.llm_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
    finally:
        await client.close()
    return runtime_config.llm_model


_MAX_LISTED_MODELS = 1000
_MAX_MODEL_PAGES = 25


def _model_sort_key(model_id: str) -> tuple[int, str]:
    name = model_id.lower()
    if name in {"orcarouter/auto", "auto"} or name.endswith("/auto"):
        return (0, name)
    return (1, name)


def _extract_model_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "models", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_model_id(item: Any) -> str:
    if isinstance(item, str):
        text = item.strip()
    elif isinstance(item, dict):
        text = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
    else:
        text = str(getattr(item, "id", "") or "").strip()
    if text.startswith("models/"):
        text = text[len("models/") :]
    return text


def _next_models_url(payload: Any, current_url: str, api_base: str) -> str:
    if not isinstance(payload, dict):
        return ""
    next_url = str(payload.get("next") or payload.get("next_page") or "").strip()
    if next_url:
        if next_url.startswith("http"):
            return next_url
        return f"{api_base.rstrip('/')}/{next_url.lstrip('/')}"
    links = payload.get("links")
    if isinstance(links, dict):
        linked = str(links.get("next") or "").strip()
        if linked:
            return linked
    if payload.get("has_more") and payload.get("last_id"):
        path = current_url.split("?", 1)[0]
        return f"{path}?after={payload['last_id']}"
    return ""


async def list_user_llm_models(*, api_key: str, api_base: str) -> list[str]:
    """Return every model id from GET {api_base}/models (OpenAI-compatible)."""
    import httpx

    key = (api_key or "").strip()
    base = (api_base or "").strip().rstrip("/")
    if not key or not base:
        raise ValueError("API key and base URL are required to list models.")

    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    url = f"{base}/models"
    ids: list[str] = []
    seen: set[str] = set()
    last_error: Exception | None = None

    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            for _ in range(_MAX_MODEL_PAGES):
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                for item in _extract_model_rows(payload):
                    model_id = _normalize_model_id(item)
                    if not model_id or model_id in seen:
                        continue
                    seen.add(model_id)
                    ids.append(model_id)
                    if len(ids) >= _MAX_LISTED_MODELS:
                        ids.sort(key=_model_sort_key)
                        return ids
                next_url = _next_models_url(payload, url, base)
                if not next_url or next_url == url:
                    break
                url = next_url
    except Exception as exc:
        last_error = exc
        try:
            ids = await _list_models_via_openai_sdk(api_key=key, api_base=base)
        except Exception as sdk_exc:
            last_error = sdk_exc

    if not ids and last_error is not None:
        raise RuntimeError(
            f"Could not list models from {base}/models: {type(last_error).__name__}: {str(last_error)[:240]}"
        ) from last_error
    ids.sort(key=_model_sort_key)
    return ids


async def _list_models_via_openai_sdk(*, api_key: str, api_base: str) -> list[str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=api_base, timeout=20.0)
    ids: list[str] = []
    seen: set[str] = set()
    try:
        async for item in client.models.list():
            model_id = _normalize_model_id(item)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            ids.append(model_id)
            if len(ids) >= _MAX_LISTED_MODELS:
                break
    finally:
        await client.close()
    return ids


__all__ = ["UserLlmClient", "create_user_llm_model", "list_user_llm_models", "probe_user_llm"]
