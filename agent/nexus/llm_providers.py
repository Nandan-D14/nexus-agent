# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Public catalog of BYOK LLM providers and E2B setup instructions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

LLM_PROVIDER_IDS = (
    "openai",
    "anthropic",
    "gemini",
    "groq",
    "openrouter",
    "orcarouter",
    "deepseek",
    "mistral",
    "xai",
    "custom",
)

_PROVIDER_ALIASES = {
    "orac": "orcarouter",
    "orca": "orcarouter",
    "orac-router": "orcarouter",
    "orca-router": "orcarouter",
    "orca_router": "orcarouter",
}


@dataclass(frozen=True)
class LlmProviderSpec:
    id: str
    name: str
    description: str
    signup_url: str
    key_url: str
    docs_url: str
    api_base: str
    default_model: str
    default_vision_model: str
    recommended_models: tuple[str, ...]
    steps: tuple[str, ...]
    notes: str = ""
    vision_warning: str = ""
    logo_url: str = ""
    logo_invert_in_dark: bool = False


E2B_SETUP: dict[str, Any] = {
    "signupUrl": "https://e2b.dev/auth/sign-up",
    "keyUrl": "https://e2b.dev/dashboard?tab=keys",
    "docsUrl": "https://www.e2b.dev/docs/api-key",
    "steps": (
        "Create an E2B account at e2b.dev/auth/sign-up. New accounts include trial credits.",
        "Open the dashboard and switch to the API keys tab.",
        "Copy your API key. It starts with e2b_.",
        "Paste the key here and save. Do not use the old E2B access-token flow; API keys are the only supported credential.",
    ),
    "notes": (
        "E2B powers the desktop sandbox for this agent. A personal API key is required "
        "before you can start a session."
    ),
    "logoUrl": "/llm-providers/e2b.svg",
    "logoInvertInDark": False,
}

PROVIDERS: tuple[LlmProviderSpec, ...] = (
    LlmProviderSpec(
        id="openai",
        name="OpenAI",
        description="GPT models with strong tool calling and vision.",
        signup_url="https://platform.openai.com/signup",
        key_url="https://platform.openai.com/api-keys",
        docs_url="https://platform.openai.com/docs/overview",
        api_base="https://api.openai.com/v1",
        default_model="gpt-4.1",
        default_vision_model="gpt-4.1",
        recommended_models=("gpt-4.1", "gpt-4o", "gpt-4o-mini", "o4-mini"),
        steps=(
            "Create or sign in to an OpenAI Platform account.",
            "Open API keys and create a secret key.",
            "Copy the key once (sk-…) and paste it here. Add billing if the key is new.",
        ),
    ),
    LlmProviderSpec(
        id="anthropic",
        name="Anthropic",
        description="Claude models via Anthropic’s OpenAI-compatible API.",
        signup_url="https://console.anthropic.com/",
        key_url="https://console.anthropic.com/settings/keys",
        docs_url="https://docs.anthropic.com/en/api/openai-sdk",
        api_base="https://api.anthropic.com/v1",
        default_model="claude-sonnet-4-5",
        default_vision_model="claude-sonnet-4-5",
        recommended_models=(
            "claude-sonnet-4-5",
            "claude-opus-4-5",
            "claude-3-5-haiku-latest",
        ),
        steps=(
            "Sign in to the Anthropic Console.",
            "Open Settings → API keys and create a key.",
            "Copy the key (sk-ant-…) and paste it here. Enable billing if prompted.",
        ),
    ),
    LlmProviderSpec(
        id="gemini",
        name="Google Gemini",
        description="Gemini models through Google AI Studio’s OpenAI-compatible endpoint.",
        signup_url="https://aistudio.google.com/",
        key_url="https://aistudio.google.com/apikey",
        docs_url="https://ai.google.dev/gemini-api/docs/openai",
        api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-2.5-flash",
        default_vision_model="gemini-2.5-flash",
        recommended_models=("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"),
        steps=(
            "Open Google AI Studio and sign in with a Google account.",
            "Create an API key and copy it.",
            "Paste the key here. This uses the OpenAI-compatible Gemini endpoint, not Vertex AI.",
        ),
        logo_invert_in_dark=False,
    ),
    LlmProviderSpec(
        id="groq",
        name="Groq",
        description="Fast open models with an OpenAI-compatible API.",
        signup_url="https://console.groq.com/",
        key_url="https://console.groq.com/keys",
        docs_url="https://console.groq.com/docs/quickstart",
        api_base="https://api.groq.com/openai/v1",
        default_model="meta-llama/llama-4-scout-17b-16e-instruct",
        default_vision_model="meta-llama/llama-4-scout-17b-16e-instruct",
        recommended_models=(
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "llama-3.3-70b-versatile",
        ),
        steps=(
            "Create a Groq Console account.",
            "Open API Keys and create a key.",
            "Paste the key here. Pick a model that supports tool calling; Llama 4 Scout also handles images.",
        ),
    ),
    LlmProviderSpec(
        id="openrouter",
        name="OpenRouter",
        description="One key for many providers (OpenAI, Anthropic, Google, and more).",
        signup_url="https://openrouter.ai/",
        key_url="https://openrouter.ai/keys",
        docs_url="https://openrouter.ai/docs/quickstart",
        api_base="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4.1-mini",
        default_vision_model="openai/gpt-4.1-mini",
        recommended_models=(
            "openai/gpt-4.1-mini",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
        ),
        steps=(
            "Sign in at openrouter.ai.",
            "Open Keys and create an API key (sk-or-v1-…).",
            "Add credits, then paste the key here. Model ids use the provider/model format.",
        ),
    ),
    LlmProviderSpec(
        id="orcarouter",
        name="OrcaRouter",
        description="One OpenAI-compatible gateway that routes across 200+ models. Use orcarouter/auto or pick a model.",
        signup_url="https://www.orcarouter.ai/",
        key_url="https://www.orcarouter.ai/",
        docs_url="https://docs.orcarouter.ai/getting-started/quickstart",
        api_base="https://api.orcarouter.ai/v1",
        default_model="orcarouter/auto",
        default_vision_model="orcarouter/auto",
        recommended_models=(
            "orcarouter/auto",
            "openai/gpt-4.1-mini",
            "anthropic/claude-sonnet-4.6",
            "google/gemini-2.5-flash",
        ),
        steps=(
            "Sign in at orcarouter.ai and copy an API key from the dashboard. Keys start with sk-orca-.",
            "Paste the key here. Models are loaded live from https://api.orcarouter.ai/v1/models.",
            "orcarouter/auto lets the router pick a live model per request. You can also choose a specific vendor/model id.",
        ),
        notes="OpenAI-compatible base URL is https://api.orcarouter.ai/v1. No token markup on the gateway.",
    ),
    LlmProviderSpec(
        id="deepseek",
        name="DeepSeek",
        description="DeepSeek chat and reasoner models.",
        signup_url="https://platform.deepseek.com/",
        key_url="https://platform.deepseek.com/api_keys",
        docs_url="https://api-docs.deepseek.com/",
        api_base="https://api.deepseek.com",
        default_model="deepseek-chat",
        default_vision_model="deepseek-chat",
        recommended_models=("deepseek-chat", "deepseek-reasoner"),
        steps=(
            "Create a DeepSeek Platform account.",
            "Open API keys and create a key.",
            "Paste the key here. DeepSeek is strongest on text; screenshot vision may be limited.",
        ),
        vision_warning="DeepSeek chat models are text-first. Desktop screenshot grounding may be unreliable.",
    ),
    LlmProviderSpec(
        id="mistral",
        name="Mistral",
        description="Mistral large models plus Pixtral for vision.",
        signup_url="https://console.mistral.ai/",
        key_url="https://console.mistral.ai/api-keys",
        docs_url="https://docs.mistral.ai/getting-started/quickstart/",
        api_base="https://api.mistral.ai/v1",
        default_model="mistral-large-latest",
        default_vision_model="pixtral-large-latest",
        recommended_models=(
            "mistral-large-latest",
            "pixtral-large-latest",
            "mistral-small-latest",
        ),
        steps=(
            "Sign in to the Mistral console.",
            "Open API keys and create a workspace key.",
            "Paste the key here. Pixtral is used by default for screenshot vision.",
        ),
    ),
    LlmProviderSpec(
        id="xai",
        name="xAI",
        description="Grok models on xAI’s OpenAI-compatible API.",
        signup_url="https://console.x.ai/",
        key_url="https://console.x.ai/",
        docs_url="https://docs.x.ai/docs/overview",
        api_base="https://api.x.ai/v1",
        default_model="grok-4",
        default_vision_model="grok-4",
        recommended_models=("grok-4", "grok-2-vision-1212", "grok-3"),
        steps=(
            "Sign in to the xAI console.",
            "Create an API key from the console home.",
            "Paste the key here and confirm the model id matches a Grok chat model you have access to.",
        ),
    ),
    LlmProviderSpec(
        id="custom",
        name="Custom",
        description="Any OpenAI-compatible chat-completions endpoint.",
        signup_url="",
        key_url="",
        docs_url="",
        api_base="",
        default_model="",
        default_vision_model="",
        recommended_models=(),
        steps=(
            "Enter the provider’s OpenAI-compatible base URL, usually ending in /v1.",
            "Enter the exact model id the provider expects.",
            "Paste a Bearer API key. The model must support tool calling; vision needs image input.",
        ),
        notes=(
            "Requests are sent as Authorization: Bearer <key> to {base}/chat/completions. "
            "Native-only APIs that are not OpenAI-compatible are not supported."
        ),
        vision_warning="Use a multimodal model if you need desktop screenshot understanding.",
    ),
)

_PROVIDERS_BY_ID = {spec.id: spec for spec in PROVIDERS}


def get_provider(provider_id: str) -> LlmProviderSpec | None:
    text = str(provider_id or "").strip().lower().replace(" ", "-")
    text = _PROVIDER_ALIASES.get(text, text)
    return _PROVIDERS_BY_ID.get(text)


def normalize_llm_provider(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    text = _PROVIDER_ALIASES.get(text, text)
    return text if text in _PROVIDERS_BY_ID else ""


def normalize_api_base(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("API base URL must be an absolute http(s) URL.")
    return text


def resolve_api_base(provider_id: str, custom_base: str = "") -> str:
    provider = normalize_llm_provider(provider_id)
    if provider == "custom":
        return normalize_api_base(custom_base)
    spec = get_provider(provider)
    return spec.api_base.rstrip("/") if spec and spec.api_base else ""


def resolve_models(
    provider_id: str,
    model: str = "",
    vision_model: str = "",
) -> tuple[str, str]:
    spec = get_provider(provider_id)
    chat = str(model or "").strip() or (spec.default_model if spec else "")
    vision = (
        str(vision_model or "").strip()
        or (spec.default_vision_model if spec else "")
        or chat
    )
    return chat, vision


def llm_config_complete(
    provider_id: str,
    api_key: str,
    api_base: str,
    model: str,
) -> bool:
    if not normalize_llm_provider(provider_id):
        return False
    if not str(api_key or "").strip() or not str(model or "").strip():
        return False
    return bool(str(api_base or "").strip())


def provider_to_public(spec: LlmProviderSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "name": spec.name,
        "description": spec.description,
        "signupUrl": spec.signup_url,
        "keyUrl": spec.key_url,
        "docsUrl": spec.docs_url,
        "apiBase": spec.api_base,
        "defaultModel": spec.default_model,
        "defaultVisionModel": spec.default_vision_model,
        "recommendedModels": list(spec.recommended_models),
        "steps": list(spec.steps),
        "notes": spec.notes,
        "visionWarning": spec.vision_warning,
        "custom": spec.id == "custom",
        "logoUrl": spec.logo_url or f"/llm-providers/{spec.id}.svg",
        "logoInvertInDark": spec.logo_invert_in_dark,
    }


def public_provider_catalog() -> list[dict[str, Any]]:
    return [provider_to_public(spec) for spec in PROVIDERS]


def e2b_setup_public() -> dict[str, Any]:
    return {
        "signupUrl": E2B_SETUP["signupUrl"],
        "keyUrl": E2B_SETUP["keyUrl"],
        "docsUrl": E2B_SETUP["docsUrl"],
        "steps": list(E2B_SETUP["steps"]),
        "notes": E2B_SETUP["notes"],
        "logoUrl": E2B_SETUP.get("logoUrl") or "/llm-providers/e2b.svg",
        "logoInvertInDark": bool(E2B_SETUP.get("logoInvertInDark", False)),
    }


def spec_from_mapping(payload: Mapping[str, Any] | None) -> LlmProviderSpec | None:
    if not isinstance(payload, Mapping):
        return None
    return get_provider(str(payload.get("id") or payload.get("llmProvider") or ""))


__all__ = [
    "E2B_SETUP",
    "LLM_PROVIDER_IDS",
    "LlmProviderSpec",
    "PROVIDERS",
    "e2b_setup_public",
    "get_provider",
    "llm_config_complete",
    "normalize_api_base",
    "normalize_llm_provider",
    "provider_to_public",
    "public_provider_catalog",
    "resolve_api_base",
    "resolve_models",
    "spec_from_mapping",
]
