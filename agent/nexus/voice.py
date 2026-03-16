"""Gemini Live API voice manager — bidirectional audio streaming."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

from google import genai
from google.genai import types

from nexus.config import settings
from nexus.usage import TokenUsageRecord, extract_token_usage_records

logger = logging.getLogger(__name__)


class VoiceConnectionError(RuntimeError):
    """Raised when the Gemini Live transport is no longer usable."""


class GeminiLiveManager:
    """Manages a persistent bidirectional Gemini Live session for voice I/O."""

    def __init__(self) -> None:
        if settings.google_project_id:
            self._client = genai.Client(
                vertexai=True,
                project=settings.google_project_id,
                location=settings.gemini_live_region,
            )
        else:
            self._client = genai.Client(api_key=settings.google_api_key)
        self._session = None
        self._live = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, system_instruction: str = "", voice_name: str = "Kore") -> None:
        """Open a Gemini Live bidirectional session."""
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
            system_instruction=system_instruction or None,
            input_audio_transcription={},
            output_audio_transcription={},
        )

        logger.info("Connecting to Gemini Live (model=%s)...", settings.gemini_live_model)
        self._session = self._client.aio.live.connect(
            model=settings.gemini_live_model, config=config
        )
        # The session is an async context manager — we enter it
        self._live = await self._session.__aenter__()
        self._connected = True
        logger.info("Gemini Live connected.")

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Forward raw PCM audio (16-bit, 16kHz, mono) from the user's mic."""
        if not self._live or not self._connected:
            raise VoiceConnectionError("Gemini Live is not connected")
        try:
            await self._live.send_realtime_input(
                audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._connected = False
            logger.warning("Gemini Live audio send failed: %s", exc)
            raise VoiceConnectionError(
                "Gemini Live connection lost while sending audio"
            ) from exc

    async def send_image(self, jpeg_bytes: bytes) -> None:
        """Send a screenshot image into the Live session for multimodal context."""
        if not self._live or not self._connected:
            raise VoiceConnectionError("Gemini Live is not connected")
        try:
            await self._live.send_realtime_input(
                media=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._connected = False
            logger.warning("Gemini Live image send failed: %s", exc)
            raise VoiceConnectionError(
                "Gemini Live connection lost while sending an image"
            ) from exc

    async def send_text(self, text: str) -> None:
        """Send text to Gemini Live (e.g., agent response for TTS)."""
        if not self._live or not self._connected:
            raise VoiceConnectionError("Gemini Live is not connected")
        try:
            await self._live.send_client_content(
                turns=types.Content(
                    role="user", parts=[types.Part(text=text)]
                ),
                turn_complete=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._connected = False
            logger.warning("Gemini Live text send failed: %s", exc)
            raise VoiceConnectionError(
                "Gemini Live connection lost while sending TTS text"
            ) from exc

    async def send_audio_end(self) -> None:
        """Signal end of an audio input stream."""
        if not self._live or not self._connected:
            raise VoiceConnectionError("Gemini Live is not connected")
        try:
            await self._live.send_realtime_input(audio_stream_end=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._connected = False
            logger.warning("Gemini Live audio end failed: %s", exc)
            raise VoiceConnectionError(
                "Gemini Live connection lost while ending audio input"
            ) from exc

    async def receive_events(self) -> AsyncGenerator[tuple[str, object | TokenUsageRecord], None]:
        """Yield events from the Gemini Live session.

        Yields tuples of:
            ("audio", bytes)            — PCM response audio at 24 kHz
            ("user_transcript", str)    — transcription of user speech
            ("agent_transcript", str)   — transcription of model speech
            ("tool_call", list)         — function calls from the model
        """
        if not self._live:
            return

        try:
            async for response in self._live.receive():
                for usage in extract_token_usage_records(
                    response,
                    default_source="voice.gemini_live",
                    default_model=settings.gemini_live_model,
                ):
                    yield ("usage", usage)

                # Response audio data (PCM 24kHz)
                if response.data is not None:
                    yield ("audio", response.data)

                if response.server_content:
                    sc = response.server_content
                    # User speech → text
                    if sc.input_transcription and sc.input_transcription.text:
                        yield ("user_transcript", sc.input_transcription.text)
                    # Model speech → text
                    if sc.output_transcription and sc.output_transcription.text:
                        yield ("agent_transcript", sc.output_transcription.text)

                # Tool / function calls
                if response.tool_call:
                    yield ("tool_call", response.tool_call.function_calls)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._connected = False
            logger.warning("Gemini Live receive loop failed: %s", exc)
            raise VoiceConnectionError(
                "Gemini Live connection lost while receiving events"
            ) from exc

    async def close(self) -> None:
        """Gracefully close the Live session."""
        try:
            if self._session:
                try:
                    await self._session.__aexit__(None, None, None)
                except Exception:
                    logger.exception("Error closing Gemini Live session")
        finally:
            self._live = None
            self._session = None
            self._connected = False
