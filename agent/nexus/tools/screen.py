"""Screenshot tool for screen observation."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
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
_last_analysis = threading.local()

_last_call_time = threading.local()
_PROMPT_VERSION = "compact-v2"
_MAX_DESCRIPTION_CHARS = 1200
_MINOR_DELTA_WINDOW_SECONDS = 4.0
_MAX_PERCEPTUAL_DISTANCE = 4


def _clip_text(value: str, limit: int = _MAX_DESCRIPTION_CHARS) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _average_hash(image: Image.Image, size: int = 8) -> int:
    grayscale = image.convert("L").resize((size, size))
    pixels = list(grayscale.getdata())
    if not pixels:
        return 0
    avg = sum(pixels) / len(pixels)
    bits = 0
    for idx, pixel in enumerate(pixels):
        if pixel >= avg:
            bits |= 1 << idx
    return bits


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _vision_cache_doc_id(screenshot_hash: str, model_id: str) -> str:
    seed = f"{screenshot_hash}:{model_id}:{_PROMPT_VERSION}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _get_persisted_analysis(session_id: str, doc_id: str) -> str | None:
    try:
        from nexus.firebase import get_firestore_client

        doc = (
            get_firestore_client()
            .collection("sessions")
            .document(session_id)
            .collection("visionCache")
            .document(doc_id)
            .get()
        )
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        description = data.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    except Exception:
        logger.debug("Vision cache lookup failed", exc_info=True)
    return None


def _store_persisted_analysis(
    session_id: str,
    doc_id: str,
    *,
    screenshot_hash: str,
    model_id: str,
    description: str,
) -> None:
    try:
        from nexus.firebase import get_firestore_client

        (
            get_firestore_client()
            .collection("sessions")
            .document(session_id)
            .collection("visionCache")
            .document(doc_id)
            .set(
                {
                    "hash": screenshot_hash,
                    "model": model_id,
                    "promptVersion": _PROMPT_VERSION,
                    "description": description,
                    "createdAt": _utcnow(),
                },
                merge=True,
            )
        )
    except Exception:
        logger.debug("Vision cache write failed", exc_info=True)


def _normalize_description(text: str) -> str:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = " ".join(raw.split()).strip()
        if not line:
            continue
        lines.append(line)
        if len(lines) >= 24:
            break
    if not lines:
        return "STATE: Screen captured. No reliable visual summary was produced."
    return _clip_text("\n".join(lines), _MAX_DESCRIPTION_CHARS)


def _build_reused_description(previous: str, *, delta: str) -> str:
    prefix = (
        "DELTA: No meaningful visual change detected since the previous screenshot. "
        "Reusing the prior screen understanding."
        if delta == "unchanged"
        else "DELTA: Only a minor visual change was detected. Reusing the prior screen understanding to save cost."
    )
    return _clip_text(f"{prefix}\n{previous}", _MAX_DESCRIPTION_CHARS)


def get_last_screenshot_b64() -> str | None:
    """Return and clear the most recent screenshot base64 PNG."""
    img = getattr(_last_screenshot, "image", None)
    _last_screenshot.image = None
    return img


def take_screenshot() -> dict:
    """Take a screenshot to see the current screen state.

    Prefer this before acting, and again after acting to verify.
    If the screen has not meaningfully changed, the tool may reuse prior screen
    understanding instead of paying for another full vision analysis.

    Returns:
        dict with a text description of all visible elements and their (x, y) coordinates.
    """
    now = time.monotonic()
    _last_call_time.t = now

    try:
        from nexus.tools._context import get_runtime_config, get_sandbox, get_session_id
        from nexus.runtime_config import build_genai_client

        sandbox = get_sandbox()
        runtime_config = get_runtime_config()
        try:
            session_id = get_session_id()
        except RuntimeError:
            session_id = ""

        # Single screenshot capture — reuse bytes for both frontend and vision
        img_bytes = sandbox.screenshot()
        img_b64 = base64.b64encode(img_bytes).decode()
        screenshot_hash = hashlib.sha256(img_bytes).hexdigest()

        # Convert to JPEG for vision analysis (smaller payload)
        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail((1324, 968))
        perceptual_hash = _average_hash(img)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        jpeg_bytes = buf.getvalue()

        vision_prompt = (
            "You are a compact screen analysis assistant for a desktop agent. "
            "The screen resolution is 1324x968 and (0,0) is the top-left corner.\n\n"
            "Return only these sections, in plain text, and keep the whole answer under 1200 characters:\n"
            "STATE: one short sentence describing the current app/page.\n"
            "FOCUS: one short sentence describing the selected or focused element.\n"
            "ELEMENTS:\n"
            "- up to 10 clickable or editable targets with approximate coordinates like Label @ (x, y)\n"
            "TEXT:\n"
            "- up to 8 important visible text snippets, errors, headings, or labels\n"
            "NEXT_ACTION: one short sentence describing the best next click or action.\n"
            "Do not include extra commentary."
        )

        try:
            cached_hash = getattr(_last_analysis, "hash", None)
            cached_description = getattr(_last_analysis, "description", None)
            cached_perceptual_hash = getattr(_last_analysis, "perceptual_hash", None)
            cached_time = float(getattr(_last_analysis, "captured_at", 0.0) or 0.0)
            model_id = runtime_config.gemini_vision_model or "vision"
            cache_doc_id = _vision_cache_doc_id(screenshot_hash, model_id)
            used_cache = False
            analysis_mode = "vision_full"
            delta = "new"
            base_description = None
            if cached_hash == screenshot_hash and isinstance(cached_description, str) and cached_description.strip():
                base_description = cached_description
                description = _build_reused_description(base_description, delta="unchanged")
                used_cache = True
                analysis_mode = "cache_exact"
                delta = "unchanged"
            elif (
                isinstance(cached_description, str)
                and cached_description.strip()
                and isinstance(cached_perceptual_hash, int)
                and cached_time > 0
                and now - cached_time <= _MINOR_DELTA_WINDOW_SECONDS
                and _hamming_distance(perceptual_hash, cached_perceptual_hash) <= _MAX_PERCEPTUAL_DISTANCE
            ):
                base_description = cached_description
                description = _build_reused_description(base_description, delta="minor_change")
                used_cache = True
                analysis_mode = "cache_delta"
                delta = "minor_change"
            elif session_id:
                persisted = _get_persisted_analysis(session_id, cache_doc_id)
                if persisted:
                    base_description = persisted
                    description = _build_reused_description(base_description, delta="unchanged")
                    used_cache = True
                    analysis_mode = "cache_exact"
                    delta = "unchanged"
                else:
                    description = None
            else:
                description = None
            if description is None and runtime_config.gemini_available:
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
                        description = _normalize_description(response.text or "")
                        base_description = description
                        model_id = model
                        analysis_mode = "vision_full"
                        delta = "changed"
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
                        "STATE: Screenshot captured.\n"
                        "FOCUS: Vision quota exhausted.\n"
                        "ELEMENTS:\n"
                        "- Use terminal inspection commands.\n"
                        "TEXT:\n"
                        "- Vision models are temporarily unavailable.\n"
                        "NEXT_ACTION: Use a terminal command or continue with a smaller step."
                    )
                if session_id:
                    _store_persisted_analysis(
                        session_id,
                        _vision_cache_doc_id(screenshot_hash, model_id),
                        screenshot_hash=screenshot_hash,
                        model_id=model_id,
                        description=description,
                    )
            else:
                description = (
                    "STATE: Screenshot captured.\n"
                    "FOCUS: Vision analysis unavailable.\n"
                    "ELEMENTS:\n"
                    "- Visual analysis is disabled for this session.\n"
                    "TEXT:\n"
                    "- No Gemini provider configured.\n"
                    "NEXT_ACTION: Use a terminal command or continue with a simpler action."
                )
        except Exception:
            logger.exception("Vision analysis failed for screenshot")
            description = (
                "STATE: Screenshot captured.\n"
                "FOCUS: Vision analysis failed.\n"
                "ELEMENTS:\n"
                "- Visual summary unavailable.\n"
                "TEXT:\n"
                "- Try a simpler action or retry once.\n"
                "NEXT_ACTION: Continue without another immediate screenshot."
            )
            base_description = description

        _last_analysis.hash = screenshot_hash
        _last_analysis.description = base_description or description
        _last_analysis.perceptual_hash = perceptual_hash
        _last_analysis.captured_at = now

        # Store the full image for the frontend (orchestrator picks it up)
        _last_screenshot.image = img_b64

        return {
            "description": description,
            "cached": used_cache,
            "hash": screenshot_hash,
            "delta": delta,
            "analysis_mode": analysis_mode,
            "model": model_id,
        }

    except Exception as e:
        logger.error("take_screenshot failed: %s", e)
        return {
            "status": "error",
            "description": f"STATE: Screenshot failed. NEXT_ACTION: Recover the sandbox before retrying. Error: {e}",
        }
