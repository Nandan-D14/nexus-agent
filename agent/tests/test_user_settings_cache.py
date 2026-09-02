# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.repositories.user_repository import UserRepository, clear_user_settings_cache


class UserSettingsCacheTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_user_settings_cache()

    def tearDown(self) -> None:
        clear_user_settings_cache()

    async def test_get_user_settings_reuses_cache(self) -> None:
        repo = UserRepository()
        calls = {"n": 0}

        def fake(_uid: str) -> dict:
            calls["n"] += 1
            return {"agentSkills": {"custom": []}, "n": calls["n"]}

        repo._get_user_settings_sync = fake  # type: ignore[method-assign]
        first = await repo.get_user_settings("user-1")
        second = await repo.get_user_settings("user-1")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(first["n"], 1)
        self.assertEqual(second["n"], 1)

    async def test_update_user_settings_busts_cache(self) -> None:
        repo = UserRepository()
        calls = {"n": 0}

        def fake_get(_uid: str) -> dict:
            calls["n"] += 1
            return {"n": calls["n"]}

        repo._get_user_settings_sync = fake_get  # type: ignore[method-assign]
        repo._update_user_settings_sync = lambda _uid, _updates: None  # type: ignore[method-assign]
        await repo.get_user_settings("user-1")
        await repo.update_user_settings("user-1", {"theme": "dark"})
        await repo.get_user_settings("user-1")
        self.assertEqual(calls["n"], 2)
