# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Provider-aware role-based model selection for Agent V2.

Supports multiple providers (qwen, bynara). The active provider is set via
MODEL_PROVIDER in settings. Model fallback tiers remain visible to the
orchestrator trace.

Roles:
  planner        — top-level loop agent (strongest tier)
  worker         — terminal worker (mid tier)
  worker_visual  — desktop/GUI worker (needs stronger visual reasoning)
  micro          — background subagents / artifact mini-agent (cheapest tier)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nexus.config import settings

if TYPE_CHECKING:
    from nexus.runtime_config import SessionRuntimeConfig

_ROLE_MODELS = {
    "planner": lambda: settings.planner_model,
    "worker": lambda: settings.worker_model,
    "worker_visual": lambda: settings.worker_visual_model,
    "micro": lambda: settings.micro_model,
}

_ROLE_FALLBACKS = {
    "planner": lambda: settings.planner_fallback_models,
    "worker": lambda: settings.worker_fallback_models,
    "worker_visual": lambda: settings.worker_visual_fallback_models,
    "micro": lambda: settings.micro_fallback_models,
}

# Bynara/DeepSeek-V4-Flash returns HTTP 504 empty bodies; other models keep
# their existing hard-fail behaviour for gateway errors.
_DEEPSEEK_V4_FLASH_MARKER = "deepseek-v4-flash"
_DEEPSEEK_V4_FLASH_GATEWAY_MARKERS = (
    "badgateway",
    "bad gateway",
    "http 504",
    "upstream returned empty body",
)


def is_deepseek_v4_flash(model: str) -> bool:
    """True for DeepSeek-V4-Flash, including the Bynara `deepseek-ai/` id."""
    return _DEEPSEEK_V4_FLASH_MARKER in (model or "").lower().replace("_", "-")


def is_deepseek_v4_flash_gateway_error(exc: BaseException | str, model: str) -> bool:
    """True when DeepSeek-V4-Flash died with a gateway 504 / empty body."""
    if not is_deepseek_v4_flash(model):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _DEEPSEEK_V4_FLASH_GATEWAY_MARKERS)


def _is_supported_text_model(model: str, *, user_llm: bool = False) -> bool:
    """Check if a model name is supported by the active provider."""
    if user_llm:
        return bool(model.strip())
    if settings.model_provider == "qwen":
        return model.lower().startswith(("qwen", "glm-"))
    # Bynara (and future providers) accept any model name — the gateway
    # handles routing.
    return bool(model.strip())


def _parse_models(value: str) -> tuple[str, ...]:
    models: list[str] = []
    for raw in value.split(","):
        model = raw.strip()
        if not model or model in models:
            continue
        if not _is_supported_text_model(model):
            raise ValueError(f"Unsupported fallback model for provider {settings.model_provider}: {model}")
        models.append(model)
    return tuple(models)


def _user_llm_configured(runtime_config: "SessionRuntimeConfig | None") -> bool:
    return bool(runtime_config is not None and runtime_config.user_llm_configured)


def model_name_for_role(
    role: str,
    runtime_config: "SessionRuntimeConfig | None" = None,
) -> str:
    if _user_llm_configured(runtime_config):
        assert runtime_config is not None
        if role == "worker_visual" and runtime_config.llm_vision_model.strip():
            model = runtime_config.llm_vision_model.strip()
        else:
            model = runtime_config.llm_model.strip()
        if not _is_supported_text_model(model, user_llm=True):
            raise ValueError(f"Role {role} resolved to unsupported model: {model}")
        return model

    runtime_names = {
        "planner": "qwen_planner_model",
        "worker": "qwen_worker_model",
        "worker_visual": "qwen_visual_model",
        "micro": "qwen_micro_model",
    }
    runtime_name = runtime_names.get(role, "qwen_worker_model")
    configured = str(getattr(runtime_config, runtime_name, "") or "").strip()
    resolver = _ROLE_MODELS.get(role) or _ROLE_MODELS["worker"]
    model = configured or resolver()
    if not _is_supported_text_model(model):
        raise ValueError(f"Role {role} resolved to unsupported model: {model}")
    return model


def model_candidates(
    role: str,
    runtime_config: "SessionRuntimeConfig | None" = None,
) -> tuple[str, ...]:
    primary = model_name_for_role(role, runtime_config)
    if _user_llm_configured(runtime_config):
        return (primary,)

    runtime_fallback_names = {
        "planner": "qwen_planner_fallback_models",
        "worker": "qwen_worker_fallback_models",
        "worker_visual": "qwen_visual_fallback_models",
        "micro": "qwen_micro_fallback_models",
    }
    runtime_values = tuple(
        str(model)
        for model in getattr(
            runtime_config,
            runtime_fallback_names.get(role, "qwen_worker_fallback_models"),
            (),
        )
        if str(model).strip()
    )
    fallback_resolver = _ROLE_FALLBACKS.get(role) or _ROLE_FALLBACKS["worker"]
    fallbacks = runtime_values or _parse_models(fallback_resolver())
    ordered: list[str] = []
    for model in (primary, *fallbacks):
        if not _is_supported_text_model(model):
            raise ValueError(f"Unsupported fallback model for provider {settings.model_provider}: {model}")
        if model not in ordered:
            ordered.append(model)
    return tuple(ordered)


def create_model(
    role: str,
    runtime_config: "SessionRuntimeConfig | None" = None,
    *,
    model_override: str | None = None,
):
    """Return a model instance for the active provider and agent role."""
    user_llm = _user_llm_configured(runtime_config)
    model_name = (model_override or "").strip() or model_name_for_role(role, runtime_config)
    if not _is_supported_text_model(model_name, user_llm=user_llm):
        raise ValueError(f"Refusing unsupported model override: {model_name}")

    if user_llm:
        from nexus.user_llm_router import create_user_llm_model
        assert runtime_config is not None
        return create_user_llm_model(model_name, runtime_config)
    if settings.model_provider == "qwen":
        from nexus.qwen_router import create_qwen_model
        return create_qwen_model(model_name)
    elif settings.model_provider == "bynara":
        from nexus.bynara_router import create_bynara_model
        return create_bynara_model(model_name)
    elif settings.model_provider == "vultr":
        from nexus.vultr_router import create_vultr_model
        return create_vultr_model(model_name)
    else:
        raise RuntimeError(f"Unknown model provider: {settings.model_provider}")


__all__ = [
    "create_model",
    "is_deepseek_v4_flash",
    "is_deepseek_v4_flash_gateway_error",
    "model_candidates",
    "model_name_for_role",
]
