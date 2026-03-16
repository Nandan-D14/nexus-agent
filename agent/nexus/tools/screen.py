"""Screenshot tool for screen observation."""

from __future__ import annotations

import base64
import io
import logging
import threading
import time

from PIL import Image

logger = logging.getLogger(__name__)

# Thread-local storage for the last screenshot image (base64 PNG).
# The orchestrator reads this after a take_screenshot tool call
# to forward the image to the frontend without bloating the LLM context.
_last_screenshot = threading.local()

# Track the last screenshot time to prevent back-to-back calls.
# If called within _COOLDOWN_SECONDS of the last call, return a reminder to act.
_COOLDOWN_SECONDS = 3.0
_last_call_time = threading.local()


def get_last_screenshot_b64() -> str | None:
    """Return and clear the most recent screenshot base64 PNG."""
    img = getattr(_last_screenshot, "image", None)
    _last_screenshot.image = None
    return img


def take_screenshot() -> dict:
    """Take a screenshot to see the current screen state.

    Call this ONCE before acting, and ONCE after acting to verify.
    Do NOT call this twice in a row — you must perform an action between calls.

    Returns:
        dict with a text description of all visible elements and their (x, y) coordinates.
    """
    # Enforce cooldown — prevent back-to-back screenshot calls without acting
    now = time.monotonic()
    last_time = getattr(_last_call_time, "t", 0.0)
    if now - last_time < _COOLDOWN_SECONDS and last_time > 0:
        _last_call_time.t = now
        return {
            "description": (
                "STOP — you just took a screenshot. Do NOT take another one. "
                "You MUST perform an action now based on what you saw in the previous screenshot. "
                "Click a button, type text, scroll, or do something. Then you can screenshot again."
            )
        }
    _last_call_time.t = now

    try:
        from nexus.tools._context import get_runtime_config, get_sandbox
        from nexus.runtime_config import build_genai_client

        sandbox = get_sandbox()
        runtime_config = get_runtime_config()

        # Single screenshot capture — reuse bytes for both frontend and vision
        img_bytes = sandbox.screenshot()
        img_b64 = base64.b64encode(img_bytes).decode()

        # Convert to JPEG for vision analysis (smaller payload)
        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail((1324, 968))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        jpeg_bytes = buf.getvalue()

        vision_prompt = (
            "You are a screen analysis assistant for an AI computer agent. "
            "The screen resolution is 1324x968 pixels, origin (0,0) top-left.\n\n"
            "Analyze this screenshot and provide:\n"
            "1. CURRENT STATE: What app/page is open? What is the user looking at?\n"
            "2. INTERACTIVE ELEMENTS: List every clickable element with its approximate (x, y) coordinates:\n"
            "   - Buttons: [name] at (x, y)\n"
            "   - Text fields/inputs: [label] at (x, y)\n"
            "   - Links: [text] at (x, y)\n"
            "   - Icons: [description] at (x, y)\n"
            "   - Menus/tabs: [name] at (x, y)\n"
            "3. TEXT CONTENT: Any readable text on screen (form labels, page content, errors, etc.)\n"
            "4. FOCUSED ELEMENT: Which element currently has focus/is selected?\n\n"
            "Be precise with coordinates. The agent will use them to click."
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
                        "free-tier quota for today. Use terminal commands like "
                        "'xdotool getactivewindow getwindowname' to inspect the screen state."
                    )
            else:
                description = (
                    "Screenshot captured but vision analysis is not available (no Gemini "
                    "provider configured). Use 'xdotool getactivewindow getwindowname' or "
                    "'wmctrl -l' to inspect window state."
                )
        except Exception:
            logger.exception("Vision analysis failed for screenshot")
            description = "Screenshot captured but vision analysis failed. Try again."

        # Store the full image for the frontend (orchestrator picks it up)
        _last_screenshot.image = img_b64

        # Append a reminder to act after viewing
        description += (
            "\n\n--- NOW PERFORM AN ACTION based on what you see above. "
            "Click, type, scroll, or interact. Do NOT call take_screenshot again until you act. ---"
        )

        # Return ONLY the description to the LLM — the base64 image would
        # blow up the context window and choke the model.
        return {"description": description}

    except Exception as e:
        logger.error("take_screenshot failed: %s", e)
        return {"status": "error", "description": f"Screenshot failed: {e}. The sandbox may have timed out."}
