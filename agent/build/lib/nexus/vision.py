"""Gemini vision — analyse screenshots using Gemini."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from google import genai
from google.genai import types

from nexus.config import settings
from nexus.sandbox import SandboxManager

logger = logging.getLogger(__name__)

# Error patterns that indicate rate-limiting / quota exhaustion
_RATE_LIMIT_PATTERNS = ("429", "resource_exhausted", "quota", "rate limit", "too many requests")


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(p in msg for p in _RATE_LIMIT_PATTERNS)


def _vision_model_list() -> list[str]:
    """Return primary model followed by configured fallbacks (de-duplicated)."""
    primary = settings.gemini_vision_model
    fallbacks = [
        m.strip()
        for m in settings.gemini_vision_fallback_models.split(",")
        if m.strip() and m.strip() != primary
    ]
    return [primary] + fallbacks


class VisionAnalyzer:
    """Sends E2B screenshots to Gemini for visual understanding."""

    def __init__(self) -> None:
        if settings.google_project_id:
            self._client = genai.Client(
                vertexai=True,
                project=settings.google_project_id,
                location=settings.google_cloud_region,
            )
        else:
            self._client = genai.Client(api_key=settings.google_api_key)

    # ── helpers ────────────────────────────────────────────────────────────

    async def _generate_with_retry(
        self,
        *,
        model: str,
        contents: list,
    ) -> str:
        """Call generate_content with per-request timeout and exponential backoff on 429.

        Returns the response text, or raises the last exception if all retries fail.
        """
        max_retries = settings.gemini_vision_max_retries
        base_wait = settings.gemini_vision_retry_base_seconds
        timeout_s = settings.gemini_vision_request_timeout_seconds
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                    ),
                    timeout=timeout_s,
                )
                return response.text or ""

            except asyncio.TimeoutError as exc:
                last_exc = exc
                wait = base_wait * (2 ** (attempt - 1))
                logger.warning(
                    "Vision request timed out after %ds (attempt %d/%d) — waiting %.0fs before retry",
                    timeout_s, attempt, max_retries, wait,
                )
                await asyncio.sleep(wait)

            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise
                last_exc = exc
                wait = base_wait * (2 ** (attempt - 1))
                logger.warning(
                    "Vision rate-limited (attempt %d/%d model=%s) — waiting %.0fs: %s",
                    attempt, max_retries, model, wait, exc,
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"Vision API failed after {max_retries} retries on model={model}: {last_exc}"
        )

    async def _generate_with_model_fallback(self, contents: list) -> str:
        """Try each model in the fallback list until one succeeds."""
        models = _vision_model_list()
        last_exc: Exception | None = None
        for model in models:
            try:
                return await self._generate_with_retry(model=model, contents=contents)
            except Exception as exc:
                last_exc = exc
                logger.warning("Vision model %s failed — trying next fallback: %s", model, exc)
        raise RuntimeError(f"All vision models failed: {last_exc}")

    # ── public API ─────────────────────────────────────────────────────────

    async def analyze_screen(
        self,
        sandbox: SandboxManager,
        task_context: str = "",
    ) -> str:
        """Take a screenshot and ask Gemini to describe what it sees.

        Returns the full analysis text.
        """
        jpeg = sandbox.screenshot_jpeg(quality=85, max_dim=1024)

        prompt = (
            "Describe what you see on this Linux desktop screenshot. "
            "List all visible windows, buttons, text, and UI elements. "
            "Be precise about element positions."
        )
        if task_context:
            prompt += f"\n\nCurrent task context: {task_context}"

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(prompt),
                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                ],
            )
        ]
        return await self._generate_with_model_fallback(contents)

    async def analyze_screen_stream(
        self,
        sandbox: SandboxManager,
        task_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """Stream analysis token by token.

        Falls back to a single non-streamed call (with retry) if the primary
        stream request fails with a rate-limit error.
        """
        jpeg = sandbox.screenshot_jpeg(quality=85, max_dim=1024)

        prompt = (
            "Describe what you see on this Linux desktop screenshot. "
            "List visible windows, buttons, text elements, and their positions."
        )
        if task_context:
            prompt += f"\n\nCurrent task context: {task_context}"

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(prompt),
                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                ],
            )
        ]

        model = settings.gemini_vision_model
        timeout_s = settings.gemini_vision_request_timeout_seconds
        try:
            async for chunk in await asyncio.wait_for(
                self._client.aio.models.generate_content_stream(
                    model=model,
                    contents=contents,
                ),
                timeout=timeout_s,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            if _is_rate_limit_error(exc) or isinstance(exc, asyncio.TimeoutError):
                logger.warning(
                    "Vision stream hit rate-limit/timeout (%s) — falling back to non-streamed retry",
                    exc,
                )
                # Degrade gracefully: run with retry and yield as a single chunk
                text = await self._generate_with_model_fallback(contents)
                if text:
                    yield text
            else:
                raise
