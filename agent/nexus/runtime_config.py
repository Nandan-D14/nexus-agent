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

logger = logging.getLogger(__name__)

GeminiProvider = Literal["apiKey", "vertex"]

_DEFAULT_GEMINI_PROVIDER: GeminiProvider = "apiKey"
_E2B_CIPHERTEXT_FIELD = "e2bApiKeyEncrypted"
_GEMINI_CIPHERTEXT_FIELD = "geminiApiKeyEncrypted"
_GEMINI_PROVIDER_FIELD = "geminiProvider"
_SHARED_ACCESS_CODE_HASH_FIELD = "sharedAccessCodeHash"


@dataclass(frozen=True)
class ByokStatus:
    e2b_key_set: bool
    gemini_key_set: bool
    gemini_provider: GeminiProvider
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
            f"kilo_gateway_url='{self.kilo_gateway_url}')"
        )

    @property
    def use_vertex_ai(self) -> bool:
        return self.gemini_provider == "vertex" and bool(self.google_project_id)

    @property
    def gemini_available(self) -> bool:
        return self.use_vertex_ai or bool(self.gemini_api_key)


def normalize_gemini_provider(value: Any) -> GeminiProvider:
    if value == "vertex":
        return "vertex"
    return _DEFAULT_GEMINI_PROVIDER


def server_vertex_configured() -> bool:
    return bool(settings.google_project_id) and _server_vertex_credentials_available()


def server_e2b_configured() -> bool:
    return bool(settings.e2b_api_key.strip())


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


def get_byok_status(user_settings: Mapping[str, Any] | None) -> ByokStatus:
    payload = get_byok_payload(user_settings)
    gemini_provider = normalize_gemini_provider(payload.get(_GEMINI_PROVIDER_FIELD))
    e2b_key_set = bool(_decrypt_or_empty(payload.get(_E2B_CIPHERTEXT_FIELD)))
    gemini_key_set = bool(_decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD)))
    vertex_configured = server_vertex_configured()
    shared_access_enabled = _shared_access_enabled(payload)
    shared_access_code_is_configured = shared_access_code_configured()
    server_e2b_is_configured = server_e2b_configured()

    can_fallback_to_api_key = gemini_key_set or (
        not settings.require_byok and bool(settings.google_api_key) and shared_access_enabled
    )

    missing: list[str] = []
    if not (e2b_key_set or (shared_access_enabled and server_e2b_is_configured)):
        missing.append("e2b")

    if gemini_provider == "vertex":
        if not (shared_access_enabled and vertex_configured) and not can_fallback_to_api_key:
            if not shared_access_enabled:
                missing.append("accessCode" if shared_access_code_is_configured else "vertex")
            else:
                missing.append("vertex")
    elif not gemini_key_set:
        missing.append("gemini")

    return ByokStatus(
        e2b_key_set=e2b_key_set,
        gemini_key_set=gemini_key_set,
        gemini_provider=gemini_provider,
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
    return {
        "requireByok": settings.require_byok or settings.beta_enforce_byok,
        "googleDriveConnected": google_drive_connected,
        "settings": raw_settings,
        "byok": {
            "e2bKeySet": status.e2b_key_set,
            "geminiKeySet": status.gemini_key_set,
            "geminiProvider": status.gemini_provider,
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

    return next_payload


def resolve_session_runtime_config(
    user_settings: Mapping[str, Any] | None,
) -> SessionRuntimeConfig:
    payload = get_byok_payload(user_settings)
    status = get_byok_status(user_settings)

    user_e2b_api_key = _decrypt_or_empty(payload.get(_E2B_CIPHERTEXT_FIELD))
    user_gemini_api_key = _decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD))
    gemini_provider = status.gemini_provider

    if user_e2b_api_key:
        e2b_api_key = user_e2b_api_key
    elif status.shared_e2b_available:
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

    if resolved_provider == "apiKey":
        agent_model = settings.gemini_api_key_agent_model
        agent_fallback_models = _parse_model_list(
            settings.gemini_api_key_agent_fallback_models,
            exclude=agent_model,
        )
    else:
        agent_model = settings.gemini_agent_model
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
        if status.shared_access_code_configured and status.server_e2b_configured:
            missing_labels.append("an E2B API key or a valid access code")
        else:
            missing_labels.append("an E2B API key")

    if "accessCode" in status.missing:
        missing_labels.append("a valid access code for shared Vertex AI credits")

    if "gemini" in status.missing:
        if status.gemini_provider == "vertex" and not status.vertex_configured:
            missing_labels.append("server-side Vertex AI configuration")
        else:
            missing_labels.append("a Gemini API key or Vertex AI")

    if "vertex" in status.missing:
        missing_labels.append("server-side Vertex AI configuration")

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
