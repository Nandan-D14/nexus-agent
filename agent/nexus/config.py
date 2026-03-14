"""Application configuration via environment variables."""

import os
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
AGENT_DIR = MODULE_DIR.parent
WORKSPACE_DIR = AGENT_DIR.parent

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(WORKSPACE_DIR / ".env"),
            str(AGENT_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # E2B Desktop
    e2b_api_key: str = ""

    # Google / Gemini
    google_api_key: str = ""
    google_project_id: str = ""
    google_cloud_region: str = "us-central1"

    # Gemini models
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_vision_model: str = "gemini-2.5-flash"

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
        return bool(self.google_api_key)

    # Server
    frontend_url: str = "http://localhost:3000"
    host: str = "0.0.0.0"
    port: int = 8000

    # Firebase
    firebase_project_id: str = ""
    google_application_credentials: str = ""
    firebase_auth_emulator_host: str = ""
    firestore_emulator_host: str = ""

    # Session
    session_timeout_minutes: int = 15
    jwt_secret: str = "dev-secret-change-in-production"

    # E2B Sandbox defaults
    sandbox_resolution_w: int = 1024
    sandbox_resolution_h: int = 768
    sandbox_timeout_seconds: int = 600
    sandbox_create_retries: int = 3
    sandbox_create_retry_backoff_seconds: float = 2.0
    sandbox_create_retry_max_seconds: float = 10.0

    # Multi-agent orchestration
    use_multi_agent: bool = True
    max_agent_turns: int = 30


settings = Settings()


def apply_runtime_env_overrides() -> None:
    """Expose env-file values to SDKs that read directly from process env."""
    if settings.google_application_credentials and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials

    if settings.firebase_auth_emulator_host and not os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = settings.firebase_auth_emulator_host

    if settings.firestore_emulator_host and not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host

    project_id = settings.firebase_project_id or settings.google_project_id
    if project_id:
        os.environ.setdefault("GCLOUD_PROJECT", project_id)
