"""Per-user runtime configuration and BYOK helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Mapping

import google.auth
from google.genai import Client, types

from nexus.config import settings
from nexus.crypto import decrypt_secret, encrypt_secret

GeminiProvider = Literal["apiKey", "vertex"]

_DEFAULT_GEMINI_PROVIDER: GeminiProvider = "apiKey"
_E2B_CIPHERTEXT_FIELD = "e2bApiKeyEncrypted"
_GEMINI_CIPHERTEXT_FIELD = "geminiApiKeyEncrypted"
_GEMINI_PROVIDER_FIELD = "geminiProvider"


@dataclass(frozen=True)
class ByokStatus:
    e2b_key_set: bool
    gemini_key_set: bool
    gemini_provider: GeminiProvider
    missing: tuple[str, ...]
    vertex_configured: bool

    @property
    def configured(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class SessionRuntimeConfig:
    e2b_api_key: str
    gemini_provider: GeminiProvider
    gemini_api_key: str
    google_project_id: str
    google_cloud_region: str
    gemini_live_model: str
    gemini_live_region: str
    gemini_vision_model: str
    gemini_vision_fallback_models: tuple[str, ...]
    use_kilo: bool
    kilo_api_key: str
    kilo_model_id: str
    kilo_gateway_url: str

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

    missing: list[str] = []
    if not e2b_key_set:
        missing.append("e2b")

    gemini_satisfied = (
        vertex_configured if gemini_provider == "vertex" else gemini_key_set
    )
    if not gemini_satisfied:
        missing.append("gemini")

    return ByokStatus(
        e2b_key_set=e2b_key_set,
        gemini_key_set=gemini_key_set,
        gemini_provider=gemini_provider,
        missing=tuple(missing),
        vertex_configured=vertex_configured,
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
        "requireByok": settings.require_byok,
        "googleDriveConnected": google_drive_connected,
        "settings": raw_settings,
        "byok": {
            "e2bKeySet": status.e2b_key_set,
            "geminiKeySet": status.gemini_key_set,
            "geminiProvider": status.gemini_provider,
            "missing": list(status.missing),
            "configured": status.configured,
            "vertexConfigured": status.vertex_configured,
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

    return next_payload


def resolve_session_runtime_config(
    user_settings: Mapping[str, Any] | None,
) -> SessionRuntimeConfig:
    payload = get_byok_payload(user_settings)
    status = get_byok_status(user_settings)

    user_e2b_api_key = _decrypt_or_empty(payload.get(_E2B_CIPHERTEXT_FIELD))
    user_gemini_api_key = _decrypt_or_empty(payload.get(_GEMINI_CIPHERTEXT_FIELD))
    gemini_provider = status.gemini_provider

    if settings.require_byok:
        e2b_api_key = user_e2b_api_key
    else:
        e2b_api_key = user_e2b_api_key or settings.e2b_api_key

    resolved_provider = _DEFAULT_GEMINI_PROVIDER
    resolved_api_key = ""
    resolved_project_id = ""

    if settings.require_byok:
        if gemini_provider == "vertex" and status.vertex_configured:
            resolved_provider = "vertex"
            resolved_project_id = settings.google_project_id
        else:
            resolved_provider = "apiKey"
            resolved_api_key = user_gemini_api_key
    else:
        if gemini_provider == "vertex" and status.vertex_configured:
            resolved_provider = "vertex"
            resolved_project_id = settings.google_project_id
        elif user_gemini_api_key:
            resolved_provider = "apiKey"
            resolved_api_key = user_gemini_api_key
        elif settings.google_api_key:
            resolved_provider = "apiKey"
            resolved_api_key = settings.google_api_key
        elif status.vertex_configured:
            resolved_provider = "vertex"
            resolved_project_id = settings.google_project_id

    return SessionRuntimeConfig(
        e2b_api_key=e2b_api_key,
        gemini_provider=resolved_provider,
        gemini_api_key=resolved_api_key,
        google_project_id=resolved_project_id,
        google_cloud_region=settings.google_cloud_region,
        gemini_live_model=settings.gemini_live_model,
        gemini_live_region=settings.gemini_live_region,
        gemini_vision_model=settings.gemini_vision_model,
        gemini_vision_fallback_models=tuple(
            model.strip()
            for model in settings.gemini_vision_fallback_models.split(",")
            if model.strip()
        ),
        use_kilo=settings.use_kilo and not settings.require_byok,
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
    return Client(
        vertexai=False,
        api_key=runtime_config.gemini_api_key,
        **client_kwargs,
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

    if "gemini" in status.missing:
        if status.gemini_provider == "vertex" and not status.vertex_configured:
            missing_labels.append("server-side Vertex AI configuration")
        else:
            missing_labels.append("a Gemini API key or Vertex AI")

    joined = " and ".join(missing_labels) if missing_labels else "your required API keys"
    return f"API & Keys setup is incomplete. Add {joined} in Settings before starting a session."


@lru_cache(maxsize=1)
def _server_vertex_credentials_available() -> bool:
    try:
        _, detected_project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except Exception:
        return False

    if detected_project_id and settings.google_project_id:
        return detected_project_id == settings.google_project_id
    return True
