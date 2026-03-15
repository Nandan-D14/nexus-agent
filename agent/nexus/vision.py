"""Gemini vision — analyse screenshots using Gemini."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from google import genai
from google.genai import types

from nexus.config import settings
from nexus.sandbox import SandboxManager

logger = logging.getLogger(__name__)


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

        response = await self._client.aio.models.generate_content(
            model=settings.gemini_vision_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(prompt),
                        types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                    ],
                )
            ],
        )
        return response.text or ""

    async def analyze_screen_stream(
        self,
        sandbox: SandboxManager,
        task_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """Stream analysis token by token."""
        jpeg = sandbox.screenshot_jpeg(quality=85, max_dim=1024)

        prompt = (
            "Describe what you see on this Linux desktop screenshot. "
            "List visible windows, buttons, text elements, and their positions."
        )
        if task_context:
            prompt += f"\n\nCurrent task context: {task_context}"

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=settings.gemini_vision_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(prompt),
                        types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                    ],
                )
            ],
        ):
            if chunk.text:
                yield chunk.text
