# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Per-user runtime configuration and BYOK helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import logging
from typing import Any, Literal, Mapping

from google.genai import Client, types

from nexus.config import settings
from nexus.crypto import decrypt_secret, encrypt_secret
from nexus.llm_providers import (
    e2b_setup_public,
    llm_config_complete,
    normalize_api_base,
    normalize_llm_provider,
    public_provider_catalog,
    resolve_api_base,
    resolve_models,
)
from nexus.policy import normalize_autonomy_mode

logger = logging.getLogger(__name__)

GeminiProvider = Literal["apiKey", "vertex"]

_DEFAULT_GEMINI_PROVIDER: GeminiProvider = "apiKey"
_E2B_CIPHERTEXT_FIELD = "e2bApiKeyEncrypted"
_GEMINI_CIPHERTEXT_FIELD = "geminiApiKeyEncrypted"
_GEMINI_PROVIDER_FIELD = "geminiProvider"
_SHARED_ACCESS_CODE_HASH_FIELD = "sharedAccessCodeHash"
_LLM_PROVIDER_FIELD = "llmProvider"
_LLM_CIPHERTEXT_FIELD = "llmApiKeyEncrypted"
_LLM_MODEL_FIELD = "llmModel"
_LLM_VISION_MODEL_FIELD = "llmVisionModel"
_LLM_API_BASE_FIELD = "llmApiBase"
_LLM_MODEL_MAX_LEN = 200
_LLM_API_BASE_MAX_LEN = 500


@dataclass(frozen=True)
class ByokStatus:
    e2b_key_set: bool
    gemini_key_set: bool
    gemini_provider: GeminiProvider
    llm_key_set: bool
    llm_provider: str
    llm_model: str
    llm_vision_model: str
    llm_api_base: str
    missing: tuple[str, ...]
    vertex_configured: bool
    shared_access_enabled: bool
    shared_access_code_configured: bool
    server_e2b_configured: bool

    @property
    def configured(self) -> bool:
        return not self.missing

    @property
    def shared_e2b_available(self) -> bool:
        return self.shared_access_enabled and self.server_e2b_configured

    @property
    def shared_vertex_available(self) -> bool:
        return self.shared_access_enabled and self.vertex_configured


@dataclass(frozen=True)
class SessionRuntimeConfig:
    e2b_api_key: str
    gemini_provider: GeminiProvider
    gemini_api_key: str
    google_project_id: str
    google_cloud_region: str
    gemini_agent_model: str
    gemini_agent_fallback_models: tuple[str, ...]
    gemini_light_model: str
    gemini_live_model: str
    gemini_live_region: str
    gemini_vision_model: str
    gemini_vision_fallback_models: tuple[str, ...]
    use_kilo: bool
    kilo_api_key: str
    kilo_model_id: str
    kilo_gateway_url: str
    qwen_planner_model: str = ""
    qwen_planner_fallback_models: tuple[str, ...] = ()
    qwen_worker_model: str = ""
    qwen_worker_fallback_models: tuple[str, ...] = ()
    qwen_visual_model: str = ""
    qwen_visual_fallback_models: tuple[str, ...] = ()
    qwen_micro_model: str = ""
    qwen_micro_fallback_models: tuple[str, ...] = ()
    qwen_vision_model: str = ""
    qwen_vision_fallback_models: tuple[str, ...] = ()
    autonomy_mode: str = "manual"
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""
    llm_vision_model: str = ""

    def __repr__(self) -> str:
        return (
            f"SessionRuntimeConfig("
            f"e2b_api_key='***', "
            f"gemini_provider='{self.gemini_provider}', "
            f"gemini_api_key='***', "
            f"google_project_id='{self.google_project_id}', "
            f"google_cloud_region='{self.google_cloud_region}', "
            f"gemini_agent_model='{self.gemini_agent_model}', "
            f"gemini_agent_fallback_models={self.gemini_agent_fallback_models}, "
            f"gemini_light_model='{self.gemini_light_model}', "
            f"gemini_live_model='{self.gemini_live_model}', "
            f"gemini_live_region='{self.gemini_live_region}', "
            f"gemini_vision_model='{self.gemini_vision_model}', "
            f"gemini_vision_fallback_models={self.gemini_vision_fallback_models}, "
            f"use_kilo={self.use_kilo}, "
            f"kilo_api_key='***', "
            f"kilo_model_id='{self.kilo_model_id}', "
            f"kilo_gateway_url='{self.kilo_gateway_url}', "
            f"qwen_planner_model='{self.qwen_planner_model}', "
            f"qwen_vision_model='{self.qwen_vision_model}', "
            f"llm_provider='{self.llm_provider}', "
            f"llm_api_key='***', "
            f"llm_api_base='{self.llm_api_base}', "
            f"llm_model='{self.llm_model}', "
            f"llm_vision_model='{self.llm_vision_model}')"
        )

    @property
    def user_llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_base and self.llm_model)

    @property
    def use_vertex_ai(self) -> bool:
        return self.gemini_provider == "vertex" and bool(self.google_project_id)

    @property
    def gemini_available(self) -> bool:
        return self.use_vertex_ai or bool(self.gemini_api_key)

    @property
    def qwen_available(self) -> bool:
        return bool(getattr(settings, "qwen_api_key", "") or getattr(settings, "bynara_api_key", ""))


def runtime_config_snapshot(runtime_config: SessionRuntimeConfig | None) -> dict[str, Any]:
    """Return durable-safe runtime metadata without API keys."""
    if runtime_config is None:
        return {}
    return {
        "gemini_provider": runtime_config.gemini_provider,
        "google_project_id_set": bool(runtime_config.google_project_id),
        "google_cloud_region": runtime_config.google_cloud_region,
        "gemini_agent_model": runtime_config.gemini_agent_model,
        "gemini_agent_fallback_models": list(runtime_config.gemini_agent_fallback_models),
        "gemini_light_model": runtime_config.gemini_light_model,
        "gemini_live_model": runtime_config.gemini_live_model,
        "gemini_live_region": runtime_config.gemini_live_region,
        "gemini_vision_model": runtime_config.gemini_vision_model,
        "gemini_vision_fallback_models": list(runtime_config.gemini_vision_fallback_models),
        "use_kilo": runtime_config.use_kilo,
        "kilo_model_id": runtime_config.kilo_model_id,
        "kilo_gateway_url_set": bool(runtime_config.kilo_gateway_url),
        "e2b_api_key_set": bool(runtime_config.e2b_api_key),
        "gemini_api_key_set": bool(runtime_config.gemini_api_key),
        "kilo_api_key_set": bool(runtime_config.kilo_api_key),
        "qwen_planner_model": runtime_config.qwen_planner_model,
        "qwen_planner_fallback_models": list(runtime_config.qwen_planner_fallback_models),
        "qwen_worker_model": runtime_config.qwen_worker_model,
        "qwen_worker_fallback_models": list(runtime_config.qwen_worker_fallback_models),
        "qwen_visual_model": runtime_config.qwen_visual_model,
        "qwen_visual_fallback_models": list(runtime_config.qwen_visual_fallback_models),
        "qwen_micro_model": runtime_config.qwen_micro_model,
        "qwen_micro_fallback_models": list(runtime_config.qwen_micro_fallback_models),
        "qwen_vision_model": runtime_config.qwen_vision_model,
        "qwen_vision_fallback_models": list(runtime_config.qwen_vision_fallback_models),
        "qwen_api_key_set": bool(getattr(settings, "qwen_api_key", "") or getattr(settings, "bynara_api_key", "")),
        "autonomy_mode": runtime_config.autonomy_mode,
        "llm_provider": runtime_config.llm_provider,
        "llm_model": runtime_config.llm_model,
        "llm_vision_model": runtime_config.llm_vision_model,
        "llm_api_base_set": bool(runtime_config.llm_api_base),
        "llm_api_key_set": bool(runtime_config.llm_api_key),
        "user_llm_configured": runtime_config.user_llm_configured,
    }


def normalize_gemini_provider(value: Any) -> GeminiProvider:
    if value == "vertex":
        return "vertex"
    return _DEFAULT_GEMINI_PROVIDER


def server_vertex_configured() -> bool:
    return bool(settings.google_project_id) and _server_vertex_credentials_available()


def server_e2b_configured() -> bool:
    return bool(settings.e2b_api_key.strip())


def byok_enforced() -> bool:
    return bool(settings.require_byok)


def shared_access_code_configured() -> bool:
    return bool(settings.shared_access_code.strip())



def _parse_model_list(value: str, *, exclude: str | None = None) -> tuple[str, ...]:
    models: list[str] = []
    seen: set[str] = set()
    excluded = (exclude or "").strip()
    for raw in value.split(","):
        model = raw.strip()
        if not model or model == excluded or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return tuple(models)


def get_byok_payload(user_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(user_settings, Mapping):
        return {}
    payload = user_settings.get("byok")
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _clip_stored_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _resolved_llm_fields(payload: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    """Return provider, api_key, api_base, model, vision_model (with Gemini migration)."""
    provider = normalize_llm_provider(payload.get(_LLM_PROVIDER_FIELD))
    llm_key = _decrypt_or_empty(payload.get(_LLM_CIPHERTEXT_FIELD))
    gemini_key = _decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD))
    if not provider and gemini_key:
        provider = "gemini"
    if not llm_key and provider in ("", "gemini") and gemini_key:
        llm_key = gemini_key
        provider = provider or "gemini"

    stored_model = str(payload.get(_LLM_MODEL_FIELD) or "").strip()
    stored_vision = str(payload.get(_LLM_VISION_MODEL_FIELD) or "").strip()
    stored_base = str(payload.get(_LLM_API_BASE_FIELD) or "").strip()
    api_base = ""
    model = stored_model
    vision = stored_vision
    if provider:
        try:
            api_base = resolve_api_base(provider, stored_base)
        except ValueError:
            api_base = ""
        model, vision = resolve_models(provider, stored_model, stored_vision)
    return provider, llm_key, api_base, model, vision


def get_byok_status(user_settings: Mapping[str, Any] | None) -> ByokStatus:
    payload = get_byok_payload(user_settings)
    gemini_provider = normalize_gemini_provider(payload.get(_GEMINI_PROVIDER_FIELD))
    e2b_key_set = bool(_decrypt_or_empty(payload.get(_E2B_CIPHERTEXT_FIELD)))
    gemini_key_set = bool(_decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD)))
    llm_provider, llm_key, llm_api_base, llm_model, llm_vision_model = _resolved_llm_fields(payload)
    llm_key_set = bool(llm_key)
    vertex_configured = server_vertex_configured()
    shared_access_enabled = _shared_access_enabled(payload)
    shared_access_code_is_configured = shared_access_code_configured()
    server_e2b_is_configured = server_e2b_configured()

    missing: list[str] = []
    if not e2b_key_set:
        missing.append("e2b")
    if not llm_config_complete(llm_provider, llm_key, llm_api_base, llm_model):
        missing.append("llm")

    return ByokStatus(
        e2b_key_set=e2b_key_set,
        gemini_key_set=gemini_key_set,
        gemini_provider=gemini_provider,
        llm_key_set=llm_key_set,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_vision_model=llm_vision_model,
        llm_api_base=llm_api_base if llm_provider == "custom" else "",
        missing=tuple(missing),
        vertex_configured=vertex_configured,
        shared_access_enabled=shared_access_enabled,
        shared_access_code_configured=shared_access_code_is_configured,
        server_e2b_configured=server_e2b_is_configured,
    )


def build_public_user_settings(user_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    status = get_byok_status(user_settings)
    raw_settings = (
        dict(user_settings.get("settings", {}))
        if isinstance(user_settings, Mapping) and isinstance(user_settings.get("settings"), Mapping)
        else {}
    )
    google_drive_connected = bool(
        user_settings.get("googleDriveRefreshToken")
        if isinstance(user_settings, Mapping)
        else None
    )
    require_byok = byok_enforced()
    return {
        "requireByok": require_byok,
        "googleDriveConnected": google_drive_connected,
        "settings": raw_settings,
        "llmProviders": public_provider_catalog(),
        "e2bSetup": e2b_setup_public(),
        "byok": {
            "e2bKeySet": status.e2b_key_set,
            "geminiKeySet": status.gemini_key_set,
            "geminiProvider": status.gemini_provider,
            "llmKeySet": status.llm_key_set,
            "llmProvider": status.llm_provider,
            "llmModel": status.llm_model,
            "llmVisionModel": status.llm_vision_model,
            "llmApiBase": status.llm_api_base,
            "missing": list(status.missing),
            "configured": status.configured,
            "vertexConfigured": status.vertex_configured,
            "sharedAccessEnabled": status.shared_access_enabled,
            "sharedAccessCodeConfigured": status.shared_access_code_configured,
            "serverE2bConfigured": status.server_e2b_configured,
        },
    }


def build_byok_storage_update(
    user_settings: Mapping[str, Any] | None,
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    payload = get_byok_payload(user_settings)
    current_provider = normalize_gemini_provider(payload.get(_GEMINI_PROVIDER_FIELD))

    next_payload = {
        _E2B_CIPHERTEXT_FIELD: payload.get(_E2B_CIPHERTEXT_FIELD),
        _GEMINI_CIPHERTEXT_FIELD: payload.get(_GEMINI_CIPHERTEXT_FIELD),
        _GEMINI_PROVIDER_FIELD: current_provider,
        _SHARED_ACCESS_CODE_HASH_FIELD: payload.get(_SHARED_ACCESS_CODE_HASH_FIELD),
        _LLM_PROVIDER_FIELD: normalize_llm_provider(payload.get(_LLM_PROVIDER_FIELD)),
        _LLM_CIPHERTEXT_FIELD: payload.get(_LLM_CIPHERTEXT_FIELD),
        _LLM_MODEL_FIELD: _clip_stored_text(payload.get(_LLM_MODEL_FIELD), _LLM_MODEL_MAX_LEN),
        _LLM_VISION_MODEL_FIELD: _clip_stored_text(
            payload.get(_LLM_VISION_MODEL_FIELD), _LLM_MODEL_MAX_LEN
        ),
        _LLM_API_BASE_FIELD: payload.get(_LLM_API_BASE_FIELD) or "",
    }

    if _GEMINI_PROVIDER_FIELD in updates:
        next_payload[_GEMINI_PROVIDER_FIELD] = normalize_gemini_provider(
            updates.get(_GEMINI_PROVIDER_FIELD)
        )

    if "e2bApiKey" in updates:
        next_payload[_E2B_CIPHERTEXT_FIELD] = _encrypt_or_clear(updates.get("e2bApiKey"))

    if "geminiApiKey" in updates:
        next_payload[_GEMINI_CIPHERTEXT_FIELD] = _encrypt_or_clear(
            updates.get("geminiApiKey")
        )

    if "accessCode" in updates:
        next_payload[_SHARED_ACCESS_CODE_HASH_FIELD] = _hash_or_clear_access_code(
            updates.get("accessCode")
        )

    if "llmProvider" in updates:
        next_payload[_LLM_PROVIDER_FIELD] = normalize_llm_provider(updates.get("llmProvider"))
        if updates.get("llmProvider") and not next_payload[_LLM_PROVIDER_FIELD]:
            raise ValueError("Unknown LLM provider.")

    if "llmApiKey" in updates:
        next_payload[_LLM_CIPHERTEXT_FIELD] = _encrypt_or_clear(updates.get("llmApiKey"))

    if "llmModel" in updates:
        next_payload[_LLM_MODEL_FIELD] = _clip_stored_text(
            updates.get("llmModel"), _LLM_MODEL_MAX_LEN
        )

    if "llmVisionModel" in updates:
        next_payload[_LLM_VISION_MODEL_FIELD] = _clip_stored_text(
            updates.get("llmVisionModel"), _LLM_MODEL_MAX_LEN
        )

    if "llmApiBase" in updates:
        next_payload[_LLM_API_BASE_FIELD] = normalize_api_base(updates.get("llmApiBase"))
        if len(str(next_payload[_LLM_API_BASE_FIELD])) > _LLM_API_BASE_MAX_LEN:
            raise ValueError("API base URL is too long.")
    elif next_payload.get(_LLM_PROVIDER_FIELD) == "custom":
        stored_base = str(next_payload.get(_LLM_API_BASE_FIELD) or "").strip()
        if stored_base:
            next_payload[_LLM_API_BASE_FIELD] = normalize_api_base(stored_base)

    # Migrate a Gemini-only save into the LLM provider fields.
    if "llmApiKey" not in updates and "geminiApiKey" in updates:
        gemini_cipher = next_payload.get(_GEMINI_CIPHERTEXT_FIELD)
        if gemini_cipher and not next_payload.get(_LLM_CIPHERTEXT_FIELD):
            next_payload[_LLM_CIPHERTEXT_FIELD] = gemini_cipher
            if not next_payload.get(_LLM_PROVIDER_FIELD):
                next_payload[_LLM_PROVIDER_FIELD] = "gemini"

    return next_payload


def resolve_session_runtime_config(
    user_settings: Mapping[str, Any] | None,
) -> SessionRuntimeConfig:
    payload = get_byok_payload(user_settings)
    status = get_byok_status(user_settings)
    public_settings = (
        user_settings.get("settings", {})
        if isinstance(user_settings, Mapping)
        and isinstance(user_settings.get("settings"), Mapping)
        else {}
    )

    user_e2b_api_key = _decrypt_or_empty(payload.get(_E2B_CIPHERTEXT_FIELD))
    user_gemini_api_key = _decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD))
    gemini_provider = status.gemini_provider
    llm_provider, llm_api_key, llm_api_base, llm_model, llm_vision_model = _resolved_llm_fields(
        payload
    )

    if user_e2b_api_key:
        e2b_api_key = user_e2b_api_key
    elif not byok_enforced() and (
        status.shared_e2b_available or server_e2b_configured()
    ):
        e2b_api_key = settings.e2b_api_key.strip()
    else:
        e2b_api_key = ""

    resolved_provider = gemini_provider
    resolved_api_key = ""
    resolved_project_id = ""

    if gemini_provider == "vertex":
        if status.shared_vertex_available:
            resolved_project_id = settings.google_project_id
        elif user_gemini_api_key:
            resolved_provider = "apiKey"
            resolved_api_key = user_gemini_api_key
        elif not settings.require_byok and settings.google_api_key and status.shared_access_enabled:
            resolved_provider = "apiKey"
            resolved_api_key = settings.google_api_key
    elif user_gemini_api_key:
        resolved_provider = "apiKey"
        resolved_api_key = user_gemini_api_key
    elif not settings.require_byok and settings.google_api_key and status.shared_access_enabled:
        resolved_provider = "apiKey"
        resolved_api_key = settings.google_api_key

    brain_model = settings.brain_model.strip()
    if resolved_provider == "apiKey":
        agent_model = brain_model or settings.gemini_api_key_agent_model
        agent_fallback_models = _parse_model_list(
            settings.gemini_api_key_agent_fallback_models,
            exclude=agent_model,
        )
    else:
        agent_model = brain_model or settings.gemini_agent_model
        agent_fallback_models = _parse_model_list(
            settings.gemini_api_key_agent_fallback_models,
            exclude=agent_model,
        )

    return SessionRuntimeConfig(
        e2b_api_key=e2b_api_key,
        gemini_provider=resolved_provider,
        gemini_api_key=resolved_api_key,
        google_project_id=resolved_project_id,
        google_cloud_region=settings.google_cloud_region,
        gemini_agent_model=agent_model,
        gemini_agent_fallback_models=agent_fallback_models,
        gemini_light_model=settings.gemini_light_model,
        gemini_live_model=settings.gemini_live_model,
        gemini_live_region=settings.gemini_live_region,
        gemini_vision_model=settings.gemini_vision_model,
        gemini_vision_fallback_models=_parse_model_list(
            settings.gemini_vision_fallback_models,
            exclude=settings.gemini_vision_model,
        ),
        use_kilo=False,
        kilo_api_key=settings.kilo_api_key,
        kilo_model_id=settings.kilo_model_id,
        kilo_gateway_url=settings.kilo_gateway_url,
        qwen_planner_model=settings.planner_model,
        qwen_planner_fallback_models=_parse_model_list(
            settings.planner_fallback_models,
            exclude=settings.planner_model,
        ),
        qwen_worker_model=settings.worker_model,
        qwen_worker_fallback_models=_parse_model_list(
            settings.worker_fallback_models,
            exclude=settings.worker_model,
        ),
        qwen_visual_model=settings.worker_visual_model,
        qwen_visual_fallback_models=_parse_model_list(
            settings.worker_visual_fallback_models,
            exclude=settings.worker_visual_model,
        ),
        qwen_micro_model=settings.micro_model,
        qwen_micro_fallback_models=_parse_model_list(
            settings.micro_fallback_models,
            exclude=settings.micro_model,
        ),
        qwen_vision_model=settings.worker_visual_model,
        qwen_vision_fallback_models=_parse_model_list(
            settings.worker_visual_fallback_models,
            exclude=settings.worker_visual_model,
        ),
        autonomy_mode=normalize_autonomy_mode(
            public_settings.get("autonomyMode") or settings.default_autonomy_mode
        ),
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_api_base=llm_api_base,
        llm_model=llm_model,
        llm_vision_model=llm_vision_model,
    )


def build_byok_error_payload(
    user_settings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status = get_byok_status(user_settings)
    return {
        "code": "BYOK_REQUIRED",
        "detail": _build_byok_error_message(status),
        "missing": list(status.missing),
    }


def build_genai_client(
    runtime_config: SessionRuntimeConfig,
    *,
    location: str | None = None,
    api_version: str | None = None,
    extra_headers: dict[str, str] | None = None,
    retry_options: types.HttpRetryOptions | None = None,
) -> Client:
    http_options_kwargs: dict[str, Any] = {}
    if extra_headers:
        http_options_kwargs["headers"] = extra_headers
    if api_version:
        http_options_kwargs["api_version"] = api_version
    if retry_options is not None:
        http_options_kwargs["retry_options"] = retry_options

    client_kwargs: dict[str, Any] = {}
    if http_options_kwargs:
        client_kwargs["http_options"] = types.HttpOptions(**http_options_kwargs)

    if runtime_config.use_vertex_ai:
        return Client(
            vertexai=True,
            project=runtime_config.google_project_id,
            location=location or runtime_config.google_cloud_region,
            **client_kwargs,
        )
    if not runtime_config.gemini_api_key:
        if runtime_config.gemini_provider == "vertex":
            raise RuntimeError(
                "Vertex AI is selected for this session, but shared Vertex access is not available."
            )
        raise RuntimeError("Gemini API key is not configured for this session.")
    return Client(
        vertexai=False,
        api_key=runtime_config.gemini_api_key,
        **client_kwargs,
    )


def ensure_selected_gemini_provider_available(
    user_settings: Mapping[str, Any] | None,
) -> None:
    status = get_byok_status(user_settings)
    if status.llm_key_set and status.llm_provider:
        return
    if status.gemini_provider != "vertex" or status.shared_vertex_available:
        return

    payload = get_byok_payload(user_settings)
    user_gemini_api_key = _decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD))
    if user_gemini_api_key:
        return
    if not settings.require_byok and settings.google_api_key and status.shared_access_enabled:
        return

    if not status.vertex_configured:
        raise PermissionError(
            "Vertex AI is selected, but it is not configured on this server. Switch to Gemini API Key."
        )

    if status.shared_access_code_configured and not status.shared_access_enabled:
        raise PermissionError(
            "Vertex AI is selected, but shared Vertex AI credits are locked for this account. "
            "Enter the access code or switch to Gemini API Key."
        )

    raise PermissionError(
        "Vertex AI is selected, but shared Vertex AI credits are not available for this account."
    )


def _encrypt_or_clear(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return encrypt_secret(text)


def _decrypt_or_empty(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        return decrypt_secret(value)
    except RuntimeError:
        return ""


def _build_byok_error_message(status: ByokStatus) -> str:
    missing_labels: list[str] = []
    if "e2b" in status.missing:
        missing_labels.append("an E2B API key")

    if "llm" in status.missing:
        missing_labels.append("an LLM provider and API key")

    joined = " and ".join(missing_labels) if missing_labels else "your required API keys"
    return f"API & Keys setup is incomplete. Add {joined} in Settings before starting a session."


def _shared_access_enabled(payload: Mapping[str, Any]) -> bool:
    stored_hash = payload.get(_SHARED_ACCESS_CODE_HASH_FIELD)
    configured_code = settings.shared_access_code.strip()
    if not isinstance(stored_hash, str) or not configured_code:
        return False
    return stored_hash == _hash_access_code(configured_code)


def _hash_or_clear_access_code(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    configured_code = settings.shared_access_code.strip()
    if not configured_code:
        raise PermissionError("Shared access codes are not enabled on this server.")
    if text != configured_code:
        raise PermissionError("Invalid access code.")
    return _hash_access_code(configured_code)


def _hash_access_code(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _server_vertex_credentials_available() -> bool:
    try:
        client = Client(
            vertexai=True,
            project=settings.google_project_id,
            location=settings.gemini_live_region or "us-central1",
        )
        models = client.models.list(config={"page_size": 1})
        next(iter(models), None)
        return True
    except Exception as exc:
        logger.warning("Vertex AI probe failed: %s", exc)
        return False
