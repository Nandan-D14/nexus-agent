# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""LiteLLM-based router for Qwen models."""

from __future__ import annotations

import logging
import os
from google.adk.models.lite_llm import LiteLlm
from nexus.config import settings

logger = logging.getLogger(__name__)

class QwenRouterClient:
    """Delegates completions to the LiteLLM Router."""

    def __init__(self, router):
        self.router = router

    async def acompletion(self, model, messages, tools, **kwargs):
        model_name = model
        if model_name.startswith("openai/"):
            model_name = model_name[len("openai/"):]
        logger.info("Routing request asynchronously to Qwen model: %s", model_name)
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
        logger.info("Routing request synchronously to Qwen model: %s", model_name)
        return self.router.completion(
            model=model_name,
            messages=messages,
            tools=tools,
            stream=stream,
            **kwargs,
        )

_qwen_router = None

def get_qwen_router():
    global _qwen_router
    if _qwen_router is None:
        from litellm import Router
        api_key = settings.qwen_api_key or os.environ.get("QWEN_API_KEY", "")
        api_base = settings.qwen_api_base or os.environ.get("QWEN_API_BASE", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        
        logger.info("Initializing Qwen Router with endpoint: %s", api_base)
        
        model_list = [
            {"model_name": "qwen3.7-max", "litellm_params": {"model": "openai/qwen3.7-max", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen3.7-plus", "litellm_params": {"model": "openai/qwen3.7-plus", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen3.6-max", "litellm_params": {"model": "openai/qwen3.6-max-preview", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen3.6-max-preview", "litellm_params": {"model": "openai/qwen3.6-max-preview", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen3.6-plus", "litellm_params": {"model": "openai/qwen3.6-plus", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen3.6-flash", "litellm_params": {"model": "openai/qwen3.6-flash", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen-max", "litellm_params": {"model": "openai/qwen-max", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen-plus", "litellm_params": {"model": "openai/qwen-plus", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen-turbo", "litellm_params": {"model": "openai/qwen-turbo", "api_key": api_key, "api_base": api_base}},
            {"model_name": "qwen-flash", "litellm_params": {"model": "openai/qwen-flash", "api_key": api_key, "api_base": api_base}},
        ]
        
        fallbacks = [
            {"qwen3.7-max": ["qwen-max", "qwen3.7-plus", "qwen-plus"]},
            {"qwen3.7-plus": ["qwen-plus", "qwen3.6-plus", "qwen-turbo"]},
            {"qwen3.6-max": ["qwen3.6-max-preview", "qwen-max", "qwen3.6-plus", "qwen-plus"]},
            {"qwen3.6-max-preview": ["qwen-max", "qwen3.6-plus", "qwen-plus"]},
            {"qwen3.6-plus": ["qwen-plus", "qwen-turbo"]},
            {"qwen3.6-flash": ["qwen-flash", "qwen-turbo"]},
            {"qwen-max": ["qwen3.7-plus", "qwen-plus"]},
            {"qwen-plus": ["qwen-turbo"]},
        ]
        
        _qwen_router = Router(model_list=model_list, fallbacks=fallbacks)
    return _qwen_router

def create_qwen_model(model_name: str) -> LiteLlm:
    """Create a LiteLlm model wrapper routed to Qwen."""
    model = LiteLlm(model=model_name)
    model.llm_client = QwenRouterClient(get_qwen_router())
    return model
