# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""LiteLLM-based router for the Vultr Inference OpenAI-compatible gateway.

Routes all model requests through https://api.vultrinference.com/v1 using
LiteLLM's Router for retry/fallback handling. When ``settings.vultr_normalize``
is enabled, the actual model sent to Vultr gets a ``-normalize`` suffix so the
gateway smooths non-standard OpenAI responses (reasoning_content, tool-call IDs,
content=None with tool_calls). The ADK-visible model name stays clean.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google.adk.models.lite_llm import LiteLlm
from nexus.config import settings
from nexus.router_common import (
    apply_request_timeout,
    apply_tool_call_policy,
    repair_tool_call_ids,
)

logger = logging.getLogger(__name__)

_vultr_router = None


class VultrRouterClient:
    """Delegates completions to the LiteLLM Router via the Vultr gateway."""

    def __init__(self, router):
        self.router = router

    async def acompletion(self, model, messages, tools, **kwargs):
        model_name = model
        if model_name.startswith("openai/"):
            model_name = model_name[len("openai/"):]
        kwargs = apply_request_timeout(apply_tool_call_policy(kwargs, tools))
        logger.info("Routing request asynchronously to Vultr model: %s", model_name)
        response = await self.router.acompletion(
            model=model_name,
            messages=messages,
            tools=tools,
            **kwargs,
        )
        if not kwargs.get("stream"):
            repair_tool_call_ids(response)
        return response

    def completion(self, model, messages, tools, stream=False, **kwargs):
        model_name = model
        if model_name.startswith("openai/"):
            model_name = model_name[len("openai/"):]
        kwargs = apply_request_timeout(apply_tool_call_policy(kwargs, tools))
        logger.info("Routing request synchronously to Vultr model: %s", model_name)
        response = self.router.completion(
            model=model_name,
            messages=messages,
            tools=tools,
            stream=stream,
            **kwargs,
        )
        if not stream:
            repair_tool_call_ids(response)
        return response


def _configured_vultr_models() -> list[str]:
    """Collect all unique model names from settings for the Vultr provider."""
    def _parse(value: str) -> list[str]:
        return [m.strip() for m in value.split(",") if m.strip()]

    models = [
        settings.planner_model,
        *_parse(settings.planner_fallback_models),
        settings.worker_model,
        *_parse(settings.worker_fallback_models),
        settings.worker_visual_model,
        *_parse(settings.worker_visual_fallback_models),
        settings.micro_model,
        *_parse(settings.micro_fallback_models),
        settings.routing_model,
        settings.routing_fallback_model,
    ]
    ordered: list[str] = []
    for model in models:
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def _upstream_model(model: str) -> str:
    """Model id sent to Vultr, with the optional normalizer suffix."""
    if settings.vultr_normalize and not model.endswith("-normalize"):
        return f"{model}-normalize"
    return model


def get_vultr_router():
    global _vultr_router
    if _vultr_router is not None:
        return _vultr_router

    from litellm import Router

    api_key = settings.vultr_api_key or os.environ.get("VULTR_API_KEY", "")
    api_base = settings.vultr_api_base or os.environ.get(
        "VULTR_API_BASE", "https://api.vultrinference.com/v1"
    )

    logger.info("Initializing Vultr Router with endpoint: %s", api_base)

    # model_name stays clean (what ADK asks for); litellm_params.model carries
    # the openai/ provider prefix and the optional -normalize suffix.
    model_list = [
        {
            "model_name": model,
            "litellm_params": {
                "model": f"openai/{_upstream_model(model)}",
                "api_key": api_key,
                "api_base": api_base,
            },
        }
        for model in _configured_vultr_models()
    ]

    _vultr_router = Router(model_list=model_list)
    return _vultr_router


def create_vultr_model(model_name: str) -> LiteLlm:
    """Create a LiteLlm model wrapper routed through the Vultr gateway."""
    model = LiteLlm(model=model_name)
    model.llm_client = VultrRouterClient(get_vultr_router())
    return model
