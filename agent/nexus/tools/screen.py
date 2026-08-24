# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

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

from nexus.resilience import call_with_deadline

logger = logging.getLogger(__name__)

# Thread-local storage for the last screenshot image (base64 PNG).
# The orchestrator reads this after a take_screenshot tool call
# to forward the image to the frontend without bloating the LLM context.
_last_screenshot = threading.local()
_last_analysis = threading.local()
_last_screen_action = threading.local()

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


def mark_screen_changed(action: str = "ui_action") -> None:
    """Mark cached visual understanding stale after an action changes the screen."""
    current_seq = int(getattr(_last_screen_action, "seq", 0) or 0)
    _last_screen_action.seq = current_seq + 1
    _last_screen_action.action = action
    _last_screen_action.changed_at = time.monotonic()


def _wait_for_screen_settle(now: float) -> tuple[float, bool, str]:
    changed_at = float(getattr(_last_screen_action, "changed_at", 0.0) or 0.0)
    action = str(getattr(_last_screen_action, "action", "") or "")
    if changed_at <= 0:
        return now, False, action
    try:
        from nexus.config import settings

        delay = max(float(settings.screenshot_after_action_delay_seconds), 0.0)
    except Exception:
        delay = 0.9
    elapsed = now - changed_at
    if delay > 0 and elapsed < delay:
        time.sleep(delay - elapsed)
        return time.monotonic(), True, action
    return now, False, action


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


def _vision_cache_timeout() -> float:
    try:
        from nexus.config import settings

        return max(float(settings.vision_cache_timeout_seconds), 0.5)
    except Exception:
        return 5.0


def _get_persisted_analysis(session_id: str, doc_id: str) -> str | None:
    def _read() -> str | None:
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
        return None

    try:
        return call_with_deadline(
            _read,
            timeout=_vision_cache_timeout(),
            label="vision cache lookup",
        )
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
    def _write() -> None:
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

    try:
        call_with_deadline(
            _write,
            timeout=_vision_cache_timeout(),
            label="vision cache write",
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


from nexus.tools.base import normalized_tool

@normalized_tool(needs_sandbox=True)
def take_screenshot() -> dict:
    """Take a screenshot to see the current screen state.

    Use this only when visual state is required.
    After UI-changing actions, the tool waits briefly so the screenshot reflects
    the latest screen instead of the previous frame.
    If the screen has not meaningfully changed, the tool may reuse prior screen
    understanding instead of paying for another full vision analysis.

    Returns:
        dict with a text description of all visible elements and their (x, y) coordinates.
    """
    now = time.monotonic()
    now, waited_for_settle, last_action = _wait_for_screen_settle(now)
    _last_call_time.t = now

    try:
        from nexus.tools._context import get_runtime_config, get_sandbox, get_session_id

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
        action_seq = int(getattr(_last_screen_action, "seq", 0) or 0)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        jpeg_bytes = buf.getvalue()

        task_context = (
            f"Observe the screen after action: {last_action}"
            if last_action
            else "Observe the current desktop state."
        )

        structured_observation: dict = {}
        vision_error = ""
        try:
            cached_hash = getattr(_last_analysis, "hash", None)
            cached_description = getattr(_last_analysis, "description", None)
            cached_perceptual_hash = getattr(_last_analysis, "perceptual_hash", None)
            cached_time = float(getattr(_last_analysis, "captured_at", 0.0) or 0.0)
            cached_action_seq = int(getattr(_last_analysis, "action_seq", -1) or -1)
            if runtime_config.user_llm_configured:
                model_id = runtime_config.llm_vision_model or runtime_config.llm_model or "user-llm"
            else:
                model_id = runtime_config.qwen_vision_model or "qwen-vision"
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
                and cached_action_seq == action_seq
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
            if description is None:
                from nexus.vision_provider import create_vision_provider

                provider = create_vision_provider(
                    runtime_config=runtime_config,
                    primary_model=(
                        (runtime_config.llm_vision_model or runtime_config.llm_model or None)
                        if runtime_config.user_llm_configured
                        else (runtime_config.qwen_vision_model or None)
                    ),
                    fallback_models=(
                        None
                        if runtime_config.user_llm_configured
                        else (runtime_config.qwen_vision_fallback_models or None)
                    ),
                )
                observation = provider.analyze(
                    jpeg_bytes,
                    width=img.width,
                    height=img.height,
                    task_context=task_context,
                )
                structured_observation = observation.to_dict()
                description = _normalize_description(observation.to_description())
                base_description = description
                model_id = observation.model
                analysis_mode = "vision_full"
                delta = "changed"
                if session_id:
                    _store_persisted_analysis(
                        session_id,
                        _vision_cache_doc_id(screenshot_hash, model_id),
                        screenshot_hash=screenshot_hash,
                        model_id=model_id,
                        description=description,
                    )
            elif not structured_observation:
                structured_observation = {
                    "visible_state": description,
                    "focus": "",
                    "targets": [],
                    "visible_text": [],
                    "errors": [],
                    "next_action": "Use a fresh observation if precise grounding is required.",
                    "confidence": 0.5,
                    "model": model_id,
                }
        except Exception as exc:
            logger.exception("Qwen vision analysis failed for screenshot")
            vision_error = str(exc)[:500] or type(exc).__name__
            next_action = (
                "Vision retries are already exhausted — do NOT call take_screenshot "
                "again for this step. Continue the task using non-visual tools "
                "(playwright_snapshot for DOM, bash/terminal output, file reads) "
                "or ask the user if the screen is genuinely required."
            )
            description = (
                "STATE: Screenshot captured, but visual analysis is unavailable.\n"
                f"FOCUS: Vision analysis failed after all configured retries.\n"
                "ELEMENTS:\n"
                "- Visual summary unavailable.\n"
                "TEXT:\n"
                f"- {vision_error}\n"
                f"NEXT_ACTION: {next_action}"
            )
            base_description = description
            structured_observation = {
                "visible_state": "Screenshot captured but vision analysis failed.",
                "focus": "",
                "targets": [],
                "visible_text": [],
                "errors": [vision_error],
                "next_action": next_action,
                "confidence": 0.0,
                "model": model_id,
            }

        _last_analysis.hash = screenshot_hash
        _last_analysis.description = base_description or description
        _last_analysis.perceptual_hash = perceptual_hash
        _last_analysis.captured_at = now
        _last_analysis.action_seq = action_seq

        # Store the full image for the frontend (orchestrator picks it up)
        _last_screenshot.image = img_b64

        # Clear the screen dirty flag — agent has now observed the current state
        from nexus.tools.screen_state import clear_dirty
        clear_dirty()

        return {
            "status": "error" if vision_error else "success",
            "description": description,
            "observation": structured_observation,
            "cached": used_cache,
            "hash": screenshot_hash,
            "delta": delta,
            "analysis_mode": analysis_mode,
            "model": model_id,
            "fresh_after_action": waited_for_settle,
            "last_action": last_action,
            "error_code": "QWEN_VISION_UNAVAILABLE" if vision_error else "",
            "error": vision_error,
        }

    except Exception as e:
        logger.error("take_screenshot failed: %s", e)
        return {
            "status": "error",
            "error_code": "SCREENSHOT_UNAVAILABLE",
            "error": str(e)[:500],
            "description": (
                "STATE: Screen capture failed after all configured retries.\n"
                "NEXT_ACTION: Do NOT keep calling take_screenshot. Continue with "
                "non-visual tools (playwright_snapshot, bash, file reads), or report "
                "that the desktop is unreachable if the task cannot proceed without it.\n"
                f"Error: {e}"
            ),
        }
