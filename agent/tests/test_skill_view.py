# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.skills import get_agent_skill, public_skill


class SkillViewTests(TestCase):
    def test_get_includes_file_bodies_and_public_strips_them(self) -> None:
        skill = get_agent_skill(None, "document-work", include_files=True)
        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertIn("files", skill)
        self.assertIn("references/deliverable-checklist.md", skill["files"])
        public = public_skill(skill)
        self.assertNotIn("files", public)
        self.assertIn("references/deliverable-checklist.md", public["resources"])
        self.assertTrue(public.get("instructions"))

    def test_unknown_skill_is_none(self) -> None:
        self.assertIsNone(get_agent_skill(None, "does-not-exist"))
