"""ADK Gemini model wrapper with explicit per-session credentials."""

from __future__ import annotations

from functools import cached_property

from google.adk.models.google_llm import Gemini
from google.genai import Client

from nexus.runtime_config import SessionRuntimeConfig, build_genai_client


class CredentialedGemini(Gemini):
    """Gemini model that does not rely on process-global env credentials."""

    def __init__(
        self,
        *,
        runtime_config: SessionRuntimeConfig,
        model: str,
    ) -> None:
        super().__init__(model=model)
        self._runtime_config = runtime_config

    @cached_property
    def api_client(self) -> Client:
        return build_genai_client(
            self._runtime_config,
            extra_headers=self._tracking_headers(),
            retry_options=self.retry_options,
        )

    @cached_property
    def _live_api_client(self) -> Client:
        return build_genai_client(
            self._runtime_config,
            location=self._runtime_config.gemini_live_region,
            api_version=self._live_api_version,
            extra_headers=self._tracking_headers(),
        )
