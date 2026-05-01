from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools.integrations import github_search_repos


class NativeIntegrationToolTests(IsolatedAsyncioTestCase):
    async def test_github_tool_reports_not_connected_without_token(self) -> None:
        with (
            patch("nexus.tools.integrations.get_history_repository", return_value=None),
            patch("nexus.tools.integrations.get_owner_id", return_value="user-1"),
        ):
            result = await github_search_repos("openai")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "GitHub is not connected for this user.")
