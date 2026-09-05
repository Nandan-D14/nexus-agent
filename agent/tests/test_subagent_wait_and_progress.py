# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from nexus.config import Settings
from nexus.orchestrator import should_deliver_soft_veto
from nexus.tools._context import set_bg_task_manager
from nexus.tools.bg_task import request_background_task


class SoftVetoTests(TestCase):
    def test_subagents_pending_is_not_soft_veto_even_with_final_text(self) -> None:
        self.assertFalse(
            should_deliver_soft_veto(
                deliver_enabled=True,
                final_response="Here is a draft answer.",
                status="partial",
                error_code="SUBAGENTS_PENDING",
            )
        )

    def test_other_advisory_codes_still_soft_veto(self) -> None:
        self.assertTrue(
            should_deliver_soft_veto(
                deliver_enabled=True,
                final_response="Done.",
                status="partial",
                error_code="UNRESOLVED_TOOL_ERROR",
            )
        )

    def test_blocked_status_is_never_soft_veto(self) -> None:
        self.assertFalse(
            should_deliver_soft_veto(
                deliver_enabled=True,
                final_response="Need approval.",
                status="blocked",
                error_code="APPROVAL_REQUIRED",
            )
        )

    def test_empty_response_is_never_soft_veto(self) -> None:
        self.assertFalse(
            should_deliver_soft_veto(
                deliver_enabled=True,
                final_response="  ",
                status="partial",
                error_code="",
            )
        )

    def test_parent_wait_default_is_under_turn_timeout(self) -> None:
        wait = Settings.model_fields["subagent_parent_wait_seconds"].default
        timeout = Settings.model_fields["agent_turn_timeout_seconds"].default
        self.assertEqual(wait, 1200)
        self.assertLess(float(wait), float(timeout))

    def test_remaining_turn_seconds_caps_subagent_wait(self) -> None:
        from unittest.mock import patch
        import time

        from nexus.config import settings
        from nexus.orchestrator import NexusOrchestrator

        orch = NexusOrchestrator.__new__(NexusOrchestrator)
        orch._turn_started_monotonic = 0.0
        with patch.object(settings, "agent_turn_timeout_seconds", 1800.0):
            self.assertGreater(orch._remaining_turn_seconds(), 0)
            orch._turn_started_monotonic = time.monotonic() - 1790
            self.assertLessEqual(orch._remaining_turn_seconds(), 0.0)


class BackgroundTaskProgressTests(IsolatedAsyncioTestCase):
    async def test_approval_emits_progress(self) -> None:
        progress: list[tuple[str, int, str]] = []

        class FakeManager:
            async def request_permission(self, description, estimated_seconds, agent="nexus"):
                return "task_ab12", True

            async def send_progress(self, task_id, value, message):
                progress.append((task_id, value, message))

        token = set_bg_task_manager(FakeManager())  # type: ignore[arg-type]
        try:
            result = await request_background_task("Install deps", 60)
        finally:
            token.var.reset(token)

        self.assertEqual(result["status"], "success")
        self.assertEqual(progress, [("task_ab12", 0, "Approved — work continues in this turn.")])


class FrontendProgressEventSourceTests(TestCase):
    def test_grouper_does_not_drop_bg_task_events(self) -> None:
        root = Path(__file__).resolve().parents[2]
        grouper = (root / "frontend" / "src" / "lib" / "turn-event-grouper.ts").read_text(
            encoding="utf-8"
        )
        utils = (root / "frontend" / "src" / "lib" / "session-utils.ts").read_text(
            encoding="utf-8"
        )
        types = (root / "frontend" / "src" / "lib" / "message-types.ts").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('event.type.startsWith("bg_task")', grouper)
        self.assertIn('event.type === "bg_task_progress"', grouper)
        self.assertIn('event.type === "subagent_progress"', grouper)
        self.assertIn('case "subagent_progress"', utils)
        self.assertIn('type: "subagent_progress"', types)
