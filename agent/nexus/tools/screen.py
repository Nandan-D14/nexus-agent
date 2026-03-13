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
        from nexus.config import settings
        from nexus.tools._context import get_sandbox

        sandbox = get_sandbox()

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
            if settings.use_vision:
                # Use Google Gemini Vision
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=settings.google_api_key)
                response = client.models.generate_content(
                    model=settings.gemini_vision_model,
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
                # Truncate to avoid bloating the LLM context
                if len(description) > 3000:
                    description = description[:3000] + "... (truncated)"
            else:
                description = (
                    "Screenshot captured. Vision analysis is not available because no Google "
                    "Gemini API key is configured. Use bash commands like 'xdotool getactivewindow "
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
