from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.fast_lookup import cache_key, clear_cache, get_cached_value, set_cached_value


class FastLookupCacheTests(TestCase):
    def tearDown(self) -> None:
        clear_cache()

    def test_cache_key_normalizes_query_text(self) -> None:
        self.assertEqual(
            cache_key("current", " Today   IPL Match ", bucket="2026-04-30"),
            cache_key("current", "today ipl match", bucket="2026-04-30"),
        )

    def test_cached_value_expires(self) -> None:
        key = cache_key("search", "Gemini docs")
        set_cached_value(key, "cached", ttl_seconds=-1)

        self.assertIsNone(get_cached_value(key))

    def test_cached_value_returns_metadata_copy(self) -> None:
        key = cache_key("search", "Gemini docs")
        set_cached_value(key, "cached", ttl_seconds=60, metadata={"result_count": 3})

        cached = get_cached_value(key)

        self.assertIsNotNone(cached)
        value, metadata = cached
        self.assertEqual(value, "cached")
        self.assertEqual(metadata["result_count"], 3)
