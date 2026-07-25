# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Application configuration via environment variables."""

import os
from pathlib import Path
from urllib.parse import urlparse


MODULE_DIR = Path(__file__).resolve().parent
AGENT_DIR = MODULE_DIR.parent
WORKSPACE_DIR = AGENT_DIR.parent

from pydantic import field_validator
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
    # Note: Gemini 3.x models require the "global" endpoint, not regional endpoints
    brain_model: str = "tencent-hy3"
    gemini_agent_model: str = "tencent-hy3"
    gemini_api_key_agent_model: str = "tencent-hy3"
    gemini_api_key_agent_fallback_models: str = (
        "gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-3.1-pro-preview"
    )
    gemini_light_model: str = "gemini-3.1-flash-lite-preview"
    gemini_live_model: str = "gemini-live-2.5-flash-native-audio"  # Live API still uses 2.5 series
    gemini_live_region: str = "us-central1"  # Live API needs a regional endpoint, not "global"
    gemini_vision_model: str = "tencent-hy3"
    # Fallback vision models tried in order when the primary hits quota/errors
    gemini_vision_fallback_models: str = "gemini-3-flash-preview,gemini-3.1-flash-lite-preview"

    # Desktop observation
    screenshot_after_action_delay_seconds: float = 0.9

    # Kilo Code (OpenAI-compatible gateway — can be used alongside Gemini)
    kilo_api_key: str = ""
    kilo_model_id: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    kilo_gateway_url: str = "https://api.kilo.ai/api/gateway"

    # Alibaba Model Studio settings (Qwen text/vision and GLM text)
    # Kept for future use — activate by setting MODEL_PROVIDER=qwen
    qwen_api_key: str = ""
    qwen_api_base: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_vision_model: str = "qwen3-vl-plus"
    qwen_vision_fallback_models: str = "qwen-vl-max,qwen-vl-plus"
    qwen_capability_probe_on_startup: bool = True

    # Bynara OpenAI-compatible gateway
    bynara_api_key: str = ""
    bynara_api_base: str = "https://router.bynara.id/v1"

    # Vultr Inference OpenAI-compatible gateway
    # Activate by setting MODEL_PROVIDER=vultr. Key belongs in .env (VULTR_API_KEY).
    vultr_api_key: str = ""
    vultr_api_base: str = "https://api.vultrinference.com/v1"
    # Append "-normalize" to model names so Vultr smooths non-standard OpenAI
    # responses (reasoning_content, tool-call IDs, content=None with tool_calls).
    vultr_normalize: bool = True

    # --- Context-window budget (prevents input > model context limit) ---
    # Active model context window (Kimi-K2.6 = 262144). The trimmer keeps the
    # per-turn prompt under context_input_budget_ratio * this limit, leaving
    # headroom for reasoning + output tokens.
    model_context_limit: int = 262144
    context_input_budget_ratio: float = 0.75
    enforce_context_budget: bool = True
    # Max characters of a single gmail_read body fed into the prompt/history.
    gmail_read_max_chars: int = 8000

    # Model roles (shared across providers)
    planner_model: str = "tencent-hy3"
    planner_fallback_models: str = "tencent-hy3"
    worker_model: str = "tencent-hy3"
    worker_fallback_models: str = "tencent-hy3"
    worker_visual_model: str = "tencent-hy3"
    worker_visual_fallback_models: str = "tencent-hy3"
    micro_model: str = "tencent-hy3"
    micro_fallback_models: str = "tencent-hy3"

    @property
    def use_kilo(self) -> bool:
        """True when Kilo is available for agent reasoning/tool calling."""
        return bool(self.kilo_api_key)

    @property
    def use_vision(self) -> bool:
        """True when Qwen multimodal screenshot analysis is available."""
        return bool(self.qwen_api_key)

    # Server
    app_env: str = "development"
    strict_config_validation: bool = False
    frontend_url: str = "http://localhost:3000"
    redis_url: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    # Firebase
    firebase_project_id: str = ""
    google_application_credentials: str = ""
    firebase_auth_emulator_host: str = ""
    firestore_emulator_host: str = ""

    # Session
    session_timeout_minutes: int = 120
    jwt_secret: str = "dev-secret-change-in-production-min-32b"

    # Durable production task runtime
    task_worker_enabled: bool = False
    # When the durable worker is enabled but Cloud Tasks is not configured,
    # run durable turns on an in-process asyncio queue so runs survive the
    # WebSocket (browser close) without requiring GCP infrastructure.
    task_queue_local_fallback: bool = True
    task_worker_auth_token: str = ""
    task_worker_lease_seconds: int = 600
    task_worker_heartbeat_interval_seconds: int = 120
    task_worker_max_attempts: int = 3
    task_worker_retry_base_seconds: int = 10
    stale_run_sweep_interval_seconds: int = 60
    durable_subagents_enabled: bool = True
    subagent_lease_seconds: int = 600
    subagent_heartbeat_interval_seconds: int = 120
    subagent_max_mailbox_messages: int = 32
    subagent_parent_wait_seconds: int = 300
    deep_research_workflow_enabled: bool = False
    deep_research_workflow_max_sources: int = 6
    task_event_replay_limit: int = 200
    default_autonomy_mode: str = "manual"  # manual | auto
    default_task_budget_credits: int = 1_000
    default_task_max_runtime_minutes: int = 60
    default_task_max_tool_calls: int = 80
    idle_sandbox_pause_seconds: int = 300

    # GCP Cloud Tasks
    gcp_tasks_project_id: str = ""
    gcp_tasks_location: str = "us-central1"
    gcp_tasks_queue: str = "cocomputer-tasks"
    gcp_tasks_worker_url: str = ""
    gcp_tasks_oidc_service_account: str = ""

    # E2B Sandbox defaults
    sandbox_resolution_w: int = 1324
    sandbox_resolution_h: int = 968
    sandbox_timeout_seconds: int = 3600
    sandbox_create_retries: int = 3
    sandbox_create_retry_backoff_seconds: float = 2.0
    sandbox_create_retry_max_seconds: float = 10.0
    # E2B template (image) id with task libraries + Chromium pre-baked. When set,
    # sandbox creation skips the boot-time `pip install` (300s) so cold starts are
    # near-instant. Leave empty to fall back to runtime provisioning.
    sandbox_template_id: str = ""
    agent_workspace_root: str = "/home/user/CoComputer/Workspaces"
    browser_cdp_port: int = 9222
    browser_startup_timeout_seconds: int = 90
    browser_startup_retry_initial_seconds: float = 0.25
    browser_startup_retry_max_seconds: float = 5.0

    # Single production orchestration path.
    max_agent_turns: int = 30

    # --- Firestore write resilience (Phase 1) ---
    # Serialize concurrent writes that touch the same shared session/task docs
    # so a single session fanning out parallel tool results does not self-
    # contend inside Firestore transactions. Different sessions stay concurrent.
    serialize_session_writes: bool = True
    # Bounded jittered-backoff retry applied on top of Firestore's own retry
    # when a transaction is Aborted due to cross-transaction contention.
    firestore_write_max_retries: int = 5
    firestore_write_backoff_base_ms: int = 50
    firestore_write_backoff_max_ms: int = 2000

    # --- Final-response guarantees (Phase 2) ---
    # When an agent turn ends with tool calls but no final text, issue one
    # additional tools-off model call so the model always produces a summary.
    force_final_synthesis: bool = True
    # Bounded re-invoke when completion verification returns a retryable
    # MISSING_FINAL_RESPONSE. 0 disables the orchestrator-level retry.
    max_final_synthesis_retries: int = 1
    # Last-resort: synthesize a partial summary from the ActionLedger evidence
    # instead of surfacing "the model ended without a final response".
    synthesize_fallback_summary_from_ledger: bool = True
    # When completion verification soft-vetoes (advisory: unresolved tool error,
    # remaining work, stale screen, missing artifact/source) but the model still
    # produced a real final response, deliver that answer with the verification
    # caveat attached instead of replacing it with the rejection text. Hard
    # failures (blocked/approval) and empty responses still fail as before.
    deliver_answer_on_soft_veto: bool = True

    # --- Reasoning-stream handling (provider-agnostic) ---
    # How the model's intermediate reasoning/chain-of-thought is surfaced:
    #   "hidden"  = never emitted to the client
    #   "compact" = a single lightweight "Thinking..." status per reasoning burst
    #   "full"    = the sanitized reasoning text (real thinking, artifacts removed)
    # Default "full": users should see the actual (cleaned) reasoning, not a stub.
    reasoning_visibility: str = "full"
    # Persist raw reasoning as role="thinking" history. Off by default so raw
    # chain-of-thought never re-enters the model's own context on later turns.
    persist_reasoning: bool = False
    # True when the active provider/model folds reasoning_content into plain
    # message text (reasoning models via OpenAI-compatible / normalize gateways,
    # e.g. Vultr -normalize + Kimi). Then non-final text is treated as reasoning.
    # Set False for providers that stream genuine partial answers as non-final.
    reasoning_is_text: bool = True

    # --- Turn idempotency ---
    # Drop a duplicate text_input with identical content for the same session
    # within this window (seconds). Guards against reconnect/replay resubmits
    # and durable+live double-runs launching the same turn twice. 0 disables.
    duplicate_turn_window_seconds: float = 10.0

    # --- Contention-free message IDs (Phase 3) ---
    # Generate time-ordered ULID message IDs + epoch-microsecond turnIndex and
    # bump messageCount via an atomic Increment, removing the shared-doc read
    # from the append hot path. Flip off to restore the legacy counter scheme.
    use_time_ordered_message_ids: bool = True

    # Single planner + AgentTool workers (docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md).
    # Fast path / mode router / artifact mini-agent were removed — every turn
    # now goes through the planner. The model tiers below control the planner
    # loop, workers, and (later) an optional turn-budget hint.
    model_provider: str = "bynara"
    # Reserved for the optional Phase B turn-budget classifier
    # (docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md §5). Currently unused; kept so
    # env-based overrides don't need re-plumbing when we ship the hint.
    routing_model: str = "tencent-hy3"
    routing_fallback_model: str = "tencent-hy3"
    max_worker_calls_per_turn: int = 8
    ask_user_timeout_seconds: float = 300.0

    # Context builder + memory (production stack Layers 1 and 4)
    memory_enabled: bool = True
    memory_max_facts: int = 12
    memory_injection_max_chars: int = 2000
    turn_context_max_chars: int = 24000
    retrieval_max_results: int = 5

    # Development-only starter entitlement
    default_plan_id: str = "starter_5"
    default_plan_name: str = "$5 Starter"
    default_plan_price_usd: int = 5
    default_credit_limit: int = 4_000
    default_credit_unit_usd: float = 0.001
    default_credit_reset_version: str = "starter_4k_reset_20260322"

    # Internal token safety cap (telemetry/debug only, not the user-facing plan allowance)
    default_token_limit: int = 100_000

    # Thesys Generative UI
    thesys_api_key: str = ""
    thesys_model: str = "c1/google/gemini-3.1-flash-lite-free/v-20251230"
    thesys_validate_timeout_seconds: float = 30.0
    thesys_skip_validation: bool = False  # Set to True to skip the live API test when saving the key (saves free-tier quota)

    # Google OAuth 2.0 (for Google Drive integration)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def pad_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            v = v.ljust(32, "x")
        return v

    @field_validator("model_provider")
    @classmethod
    def validate_model_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ("qwen", "bynara", "vultr"):
            raise ValueError("MODEL_PROVIDER must be 'qwen', 'bynara', or 'vultr'")
        return normalized

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

    if settings.jwt_secret in {
        "dev-secret-change-in-production",
        "change-this-in-production",
        "dev-secret-change-in-production-min-32b",
        "dev-secret-change-in-production-min-32-bytes-long",
    }:
        issues.append("JWT_SECRET must be set to a non-default value")
    if len(settings.jwt_secret.encode("utf-8")) < 32:
        issues.append("JWT_SECRET must be at least 32 bytes for HS256")
    if parsed_frontend.scheme not in {"http", "https"} or not parsed_frontend.netloc:
        issues.append("FRONTEND_URL must be a valid absolute http(s) URL")
    if not settings.firebase_project_id and not settings.firebase_auth_emulator_host:
        issues.append("FIREBASE_PROJECT_ID or FIREBASE_AUTH_EMULATOR_HOST must be configured")
    if not settings.require_byok and not settings.e2b_api_key:
        issues.append("E2B_API_KEY is required when REQUIRE_BYOK is false")
    if not settings.qwen_api_key:
        issues.append("QWEN_API_KEY is required for Model Studio Qwen/GLM reasoning and Qwen vision")
    if settings.model_provider == "vultr" and not settings.vultr_api_key:
        issues.append("VULTR_API_KEY is required when MODEL_PROVIDER is 'vultr'")
    if bool(settings.google_oauth_client_id) != bool(settings.google_oauth_client_secret):
        issues.append("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be configured together")
    if settings.beta_access_enabled and not settings.beta_admin_emails.strip():
        issues.append("BETA_ADMIN_EMAILS must include at least one admin email")
    if settings.beta_access_enabled and not settings.beta_google_sheet_id.strip():
        issues.append("BETA_GOOGLE_SHEET_ID must be configured for beta application sync")
    if not settings.byok_encryption_key.strip():
        issues.append("BYOK_ENCRYPTION_KEY must be configured for credential safety")
    if settings.is_production:
        if not settings.task_worker_enabled:
            issues.append("TASK_WORKER_ENABLED must be true in production")
        elif not (
            settings.gcp_tasks_project_id
            and settings.gcp_tasks_location
            and settings.gcp_tasks_queue
            and settings.gcp_tasks_worker_url
        ):
            issues.append(
                "Cloud Tasks project, location, queue, and worker URL are required "
                "when TASK_WORKER_ENABLED is true in production"
            )
        if settings.task_queue_local_fallback:
            issues.append("TASK_QUEUE_LOCAL_FALLBACK must be false in production")
        if settings.task_worker_enabled and not settings.task_worker_auth_token:
            issues.append("TASK_WORKER_AUTH_TOKEN is required in production")
        if not settings.durable_subagents_enabled:
            issues.append("DURABLE_SUBAGENTS_ENABLED must be true in production")
        if settings.subagent_lease_seconds <= 0:
            issues.append("SUBAGENT_LEASE_SECONDS must be positive")
        if not (
            0
            < settings.subagent_heartbeat_interval_seconds
            < settings.subagent_lease_seconds
        ):
            issues.append(
                "SUBAGENT_HEARTBEAT_INTERVAL_SECONDS must be positive and "
                "less than SUBAGENT_LEASE_SECONDS"
            )
        if settings.subagent_max_mailbox_messages < 4:
            issues.append("SUBAGENT_MAX_MAILBOX_MESSAGES must be at least 4")
        if settings.subagent_parent_wait_seconds <= 0:
            issues.append("SUBAGENT_PARENT_WAIT_SECONDS must be positive")

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


def get_oauth_client_secret() -> str:
    """Fetch the OAuth client secret from Secret Manager or fallback to settings."""
    if settings.google_oauth_client_secret:
        return settings.google_oauth_client_secret
        
    project_id = settings.google_project_id or settings.firebase_project_id
    if not project_id:
        return ""
        
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/google-oauth-client-secret/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to load OAuth secret from Secret Manager: %s", e)
        return ""
