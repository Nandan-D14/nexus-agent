"""Small in-memory cache for fast-path lookups."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import time
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    metadata: dict[str, Any]


_CACHE: dict[str, CacheEntry] = {}
_SPACE_RE = re.compile(r"\s+")


def normalize_cache_text(value: str) -> str:
    return _SPACE_RE.sub(" ", (value or "").strip().lower())


def cache_key(kind: str, query: str, *, bucket: str = "") -> str:
    seed = f"{kind}:{bucket}:{normalize_cache_text(query)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"


def get_cached_value(key: str) -> tuple[Any, dict[str, Any]] | None:
    entry = _CACHE.get(key)
    if not entry:
        return None
    if entry.expires_at <= time.monotonic():
        _CACHE.pop(key, None)
        return None
    return entry.value, dict(entry.metadata)


def set_cached_value(
    key: str,
    value: Any,
    *,
    ttl_seconds: float,
    metadata: dict[str, Any] | None = None,
) -> None:
    if ttl_seconds <= 0:
        return
    _CACHE[key] = CacheEntry(
        value=value,
        expires_at=time.monotonic() + ttl_seconds,
        metadata=dict(metadata or {}),
    )


def clear_cache() -> None:
    _CACHE.clear()
