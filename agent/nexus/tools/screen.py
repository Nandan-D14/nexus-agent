"""Screenshot tool for screen observation."""

from __future__ import annotations

import base64
import logging
import threading

logger = logging.getLogger(__name__)

# Thread-local storage for the last screenshot image (base64 PNG).
# The orchestrator reads this after a take_screenshot tool call
# to forward the image to the frontend without bloating the LLM context.
_last_screenshot = threading.local()


def get_last_screenshot_b64() -> str | None:
    """Return and clear the most recent screenshot base64 PNG."""
    img = getattr(_last_screenshot, "image", None)
    _last_screenshot.image = None
    return img


def take_screenshot() -> dict:
    """Take a screenshot of the current screen to see what is displayed.

    ALWAYS call this tool:
    - Before starting any task (to see the current state)
    - After every GUI action (click, type, open) to verify results
    - When you need to read text on screen
    - When you need to find where to click

    Returns:
        dict with a text description of the screen and a base64 PNG for the frontend.
    """
    try:
        from nexus.tools._context import get_runtime_config, get_sandbox
        from nexus.runtime_config import build_genai_client

        sandbox = get_sandbox()
        runtime_config = get_runtime_config()

        # Raw PNG for forwarding to the frontend
        img_bytes = sandbox.screenshot()
        img_b64 = base64.b64encode(img_bytes).decode()

        # Smaller JPEG for vision analysis
        jpeg_bytes = sandbox.screenshot_jpeg(quality=85, max_dim=1024)

        vision_prompt = (
            "Describe exactly what you see on this Linux desktop screenshot. "
            "List all visible windows, UI elements, buttons, text fields, "
            "icons, menus, and any readable text. Be precise about element "
            "positions (left/right/top/bottom/center). Note which element "
            "appears focused or active."
        )

        try:
            if runtime_config.gemini_available:
                from google.genai import types
                from google.genai.errors import ClientError

                client = build_genai_client(runtime_config)

                # Build ordered list of models to try: primary first, then fallbacks
                models_to_try = [
                    runtime_config.gemini_vision_model,
                    *[
                        model
                        for model in runtime_config.gemini_vision_fallback_models
                        if model != runtime_config.gemini_vision_model
                    ],
                ]

                description = None
                last_error: Exception | None = None
                for model in models_to_try:
                    try:
                        response = client.models.generate_content(
                            model=model,
                            contents=[
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part(text=vision_prompt),
                                        types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                                    ],
                                )
                            ],
                        )
                        description = response.text or "Analysis returned empty."
                        if len(description) > 3000:
                            description = description[:3000] + "... (truncated)"
                        break  # success
                    except ClientError as exc:
                        last_error = exc
                        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                        if status == 429 or "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                            logger.warning(
                                "Vision model %s quota exhausted (429), trying next fallback.",
                                model,
                            )
                            continue
                        raise  # non-quota error — propagate

                if description is None:
                    logger.error(
                        "All vision models exhausted quota. Last error: %s", last_error
                    )
                    description = (
                        "Screenshot captured but all vision models have exhausted their "
                        "free-tier quota for today. Navigating by text commands (bash/xdotool) "
                        "is still available."
                    )
            else:
                description = (
                    "Screenshot captured. Vision analysis is not available because no Google "
                    "Gemini provider is configured for this session. Use bash commands like 'xdotool getactivewindow "
                    "getwindowname' or 'wmctrl -l' to inspect window state, or use xdotool for "
                    "mouse and keyboard actions."
                )
        except Exception:
            logger.exception("Vision analysis failed for screenshot")
            description = "Screenshot captured but vision analysis failed. Try again."

        # Store the full image for the frontend (orchestrator picks it up)
        _last_screenshot.image = img_b64

        # Return ONLY the description to the LLM — the base64 image would
        # blow up the context window and choke the model.
        return {"description": description}

    except Exception as e:
        logger.error("take_screenshot failed: %s", e)
        return {"status": "error", "description": f"Screenshot failed: {e}. The sandbox may have timed out."}
