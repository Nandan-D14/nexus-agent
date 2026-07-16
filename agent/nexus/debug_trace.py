"""Temporary runtime trace sink for debug session a2c6df."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any


# region agent log
_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-a2c6df.log"


def emit_debug_trace(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
) -> None:
    """Append a safe, compact NDJSON trace without affecting agent execution."""
    timestamp = int(time.time() * 1000)
    payload = {
        "sessionId": "a2c6df",
        "id": f"a2c6df-{timestamp}-{location.rsplit(':', 1)[0].replace('.', '-')}",
        "timestamp": timestamp,
        "runId": run_id or "unbound",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
    }
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), default=lambda value: type(value).__name__) + "\n")
    except Exception:
        pass
# endregion agent log
