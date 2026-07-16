# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""LiteLLM-based router for the Bynara OpenAI-compatible gateway.

Routes all model requests through https://router.bynara.id/v1 using
LiteLLM's Router for retry/fallback handling.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google.adk.models.lite_llm import LiteLlm
from nexus.config import settings

logger = logging.getLogger(__name__)

_bynara_router = None


class BynaraRouterClient:
    """Delegates completions to the LiteLLM Router via the Bynara gateway."""

    def __init__(self, router):
        self.router = router

    async def acompletion(self, model, messages, tools, **kwargs):
        model_name = model
        if model_name.startswith("openai/"):
            model_name = model_name[len("openai/"):]
        logger.info("Routing request asynchronously to Bynara model: %s", model_name)
        return await self.router.acompletion(
            model=model_name,
            messages=messages,
            tools=tools,
            **kwargs,
        )

    def completion(self, model, messages, tools, stream=False, **kwargs):
        model_name = model
        if model_name.startswith("openai/"):
            model_name = model_name[len("openai/"):]
        logger.info("Routing request synchronously to Bynara model: %s", model_name)
        return self.router.completion(
            model=model_name,
            messages=messages,
            tools=tools,
            stream=stream,
            **kwargs,
        )


def _configured_bynara_models() -> list[str]:
    """Collect all unique model names from settings for the Bynara provider."""
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


def get_bynara_router():
    global _bynara_router
    if _bynara_router is not None:
        return _bynara_router

    from litellm import Router

    api_key = settings.bynara_api_key or os.environ.get("BYNARA_API_KEY", "")
    api_base = settings.bynara_api_base or os.environ.get(
        "BYNARA_API_BASE", "https://router.bynara.id/v1"
    )

    logger.info("Initializing Bynara Router with endpoint: %s", api_base)

    model_list = [
        {
            "model_name": model,
            "litellm_params": {
                "model": f"openai/{model}",
                "api_key": api_key,
                "api_base": api_base,
            },
        }
        for model in _configured_bynara_models()
    ]

    _bynara_router = Router(model_list=model_list)
    return _bynara_router


def create_bynara_model(model_name: str) -> LiteLlm:
    """Create a LiteLlm model wrapper routed through the Bynara gateway."""
    model = LiteLlm(model=model_name)
    model.llm_client = BynaraRouterClient(get_bynara_router())
    return model
