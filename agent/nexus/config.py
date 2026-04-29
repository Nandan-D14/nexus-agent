"""Application configuration via environment variables."""

import os
from pathlib import Path
from urllib.parse import urlparse


MODULE_DIR = Path(__file__).resolve().parent
AGENT_DIR = MODULE_DIR.parent
WORKSPACE_DIR = AGENT_DIR.parent

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(AGENT_DIR / ".env"),
            str(WORKSPACE_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # E2B Desktop
    e2b_api_key: str = ""

    # BYO keys
    require_byok: bool = False
    byok_encryption_key: str = ""
    shared_access_code: str = ""
    # Future use: keep the controlled beta/access-code system in the codebase,
    # but ship internal testing with the gate disabled by default.
    beta_access_enabled: bool = False
    beta_enforce_byok: bool = True
    beta_admin_emails: str = ""
    beta_google_sheet_id: str = ""
    beta_google_sheet_name: str = "beta_applications"

    # Google / Gemini
    google_api_key: str = ""
    google_project_id: str = ""
    google_cloud_region: str = "global"  # For Gemini 3 vision/agent (must be "global")

    # Gemini models
    # Note: Gemini 3 models require the "global" endpoint, not regional endpoints
    gemini_agent_model: str = "gemini-3-flash-preview"  # Gemini 3 Flash (Vertex AI)
    gemini_api_key_agent_model: str = "gemini-3-flash-preview"
    gemini_api_key_agent_fallback_models: str = (
        "gemini-3-flash-preview,gemini-3.1-flash-lite-preview"
    )
    gemini_light_model: str = "gemini-3.1-flash-lite-preview"
    gemini_live_model: str = "gemini-live-2.5-flash-native-audio"  # Live API still uses 2.5 series
    gemini_live_region: str = "us-central1"  # Live API needs a regional endpoint, not "global"
    gemini_vision_model: str = "gemini-3-flash-preview"
    # Fallback vision models tried in order when the primary hits quota/errors
    gemini_vision_fallback_models: str = "gemini-3-flash-preview,gemini-3.1-flash-lite-preview"

    # Kilo Code (OpenAI-compatible gateway — can be used alongside Gemini)
    kilo_api_key: str = ""
    kilo_model_id: str = "minimax/minimax-m2.5:free"
    kilo_gateway_url: str = "https://api.kilo.ai/api/gateway"

    @property
    def use_kilo(self) -> bool:
        """True when Kilo is available for agent reasoning/tool calling."""
        return bool(self.kilo_api_key)

    @property
    def use_vision(self) -> bool:
        """True when Gemini vision is available for screenshot analysis."""
        return bool(self.google_api_key or self.google_project_id)

    # Server
    app_env: str = "development"
    strict_config_validation: bool = False
    frontend_url: str = "http://localhost:3000"
    host: str = "0.0.0.0"
    port: int = 8000

    # Firebase
    firebase_project_id: str = ""
    google_application_credentials: str = ""
    firebase_auth_emulator_host: str = ""
    firestore_emulator_host: str = ""

    # Session
    session_timeout_minutes: int = 120
    jwt_secret: str = "dev-secret-change-in-production"

    # E2B Sandbox defaults
    sandbox_resolution_w: int = 1324
    sandbox_resolution_h: int = 968
    sandbox_timeout_seconds: int = 3600
    sandbox_create_retries: int = 3
    sandbox_create_retry_backoff_seconds: float = 2.0
    sandbox_create_retry_max_seconds: float = 10.0
    agent_workspace_root: str = "/home/user/CoComputer/Workspaces"

    # Multi-agent orchestration
    use_multi_agent: bool = True
    max_agent_turns: int = 30

    # Development-only starter entitlement
    default_plan_id: str = "starter_5"
    default_plan_name: str = "$5 Starter"
    default_plan_price_usd: int = 5
    default_credit_limit: int = 4_000
    default_credit_unit_usd: float = 0.001
    default_credit_reset_version: str = "starter_4k_reset_20260322"

    # Internal token safety cap (telemetry/debug only, not the user-facing plan allowance)
    default_token_limit: int = 100_000

    # Google OAuth 2.0 (for Google Drive integration)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production" or bool(os.environ.get("K_SERVICE"))


settings = Settings()


def validate_startup_settings() -> None:
    """Fail fast on unsafe production config."""
    if not (settings.is_production or settings.strict_config_validation):
        return

    issues: list[str] = []
    parsed_frontend = urlparse(settings.frontend_url)

    if settings.jwt_secret in {"dev-secret-change-in-production", "change-this-in-production"}:
        issues.append("JWT_SECRET must be set to a non-default value")
    if parsed_frontend.scheme not in {"http", "https"} or not parsed_frontend.netloc:
        issues.append("FRONTEND_URL must be a valid absolute http(s) URL")
    if not settings.firebase_project_id and not settings.firebase_auth_emulator_host:
        issues.append("FIREBASE_PROJECT_ID or FIREBASE_AUTH_EMULATOR_HOST must be configured")
    if not settings.require_byok and not settings.e2b_api_key:
        issues.append("E2B_API_KEY is required when REQUIRE_BYOK is false")
    if not settings.require_byok and not (
        settings.google_api_key
        or settings.google_project_id
        or settings.kilo_api_key
    ):
        issues.append("A server-side model provider must be configured when REQUIRE_BYOK is false")
    if bool(settings.google_oauth_client_id) != bool(settings.google_oauth_client_secret):
        issues.append("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be configured together")
    if settings.beta_access_enabled and not settings.beta_admin_emails.strip():
        issues.append("BETA_ADMIN_EMAILS must include at least one admin email")
    if settings.beta_access_enabled and not settings.beta_google_sheet_id.strip():
        issues.append("BETA_GOOGLE_SHEET_ID must be configured for beta application sync")

    if issues:
        joined = "; ".join(issues)
        raise RuntimeError(f"Invalid production configuration: {joined}")


def apply_runtime_env_overrides() -> None:
    """Expose env-file values only where process-global env is still required."""
    # NOTE: We intentionally do NOT set GOOGLE_APPLICATION_CREDENTIALS in os.environ
    # when Vertex AI is configured, because that env var is global — both Firebase
    # Admin SDK and the genai/Vertex AI SDK read it.  The Firebase SA key is from a
    # different project and has no Vertex AI permissions.  Instead, Firebase Admin is
    # initialized with explicit credentials in firebase.py, and genai uses ADC.
    if settings.google_application_credentials and not settings.google_project_id:
        # API-key mode (no Vertex AI) — safe to export for Firebase
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials

    if settings.firebase_auth_emulator_host and not os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = settings.firebase_auth_emulator_host

    if settings.firestore_emulator_host and not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host

    project_id = settings.firebase_project_id or settings.google_project_id
    if project_id:
        os.environ.setdefault("GCLOUD_PROJECT", project_id)

    if not settings.require_byok:
        # Expose Google API key for any legacy SDK paths that still read process env.
        if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = settings.google_api_key

        # Keep project/location available for SDKs that inspect them directly, but do
        # not force Vertex mode globally. Gemini API-key clients must opt in/out
        # explicitly per request to avoid cross-user auth leakage.
        if settings.google_project_id:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_project_id)
        if settings.google_cloud_region:
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_region)

    # Allow oauthlib to use HTTP (non-HTTPS) redirect URIs during local development
    if settings.frontend_url.startswith("http://"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
