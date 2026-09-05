# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.skills import build_enabled_skills_prompt, build_skill_prompt_for_agent, list_agent_skills, skill_from_parsed
from nexus.skill_format import parse_skill_md, render_skill_md, safe_skill_relpath
from nexus.tools.skills import read_skill, read_skill_file


class AgentSkillsPromptTests(TestCase):
    def test_prompt_tells_agent_to_select_matching_skills_before_tools(self) -> None:
        prompt = build_enabled_skills_prompt(None)

        self.assertIn("scan this skill catalog", prompt)
        self.assertIn("read_skill(skill_id)", prompt)
        self.assertIn("read_skill_file(skill_id, path)", prompt)
        self.assertIn("not a connector by itself", prompt)
        self.assertIn("codebase-engineering", prompt)
        self.assertNotIn("Instructions:", prompt)
        self.assertNotIn("Read the code first, keep edits scoped", prompt)

    def test_v2_agents_receive_matching_default_skills(self) -> None:
        planner_prompt = build_skill_prompt_for_agent(None, "nexus_planner")
        terminal_prompt = build_skill_prompt_for_agent(None, "terminal_worker")
        desktop_prompt = build_skill_prompt_for_agent(None, "desktop_worker")

        self.assertIn("browser-research", planner_prompt)
        self.assertIn("codebase-engineering", planner_prompt)
        self.assertIn("codebase-engineering", terminal_prompt)
        self.assertIn("desktop-control", desktop_prompt)

    def test_bundled_playbooks_expose_resources(self) -> None:
        skills = {skill["skill_id"]: skill for skill in list_agent_skills(None)}
        self.assertIn("references/deliverable-checklist.md", skills["document-work"]["resources"])
        self.assertIn("scripts/csv_preview.py", skills["spreadsheet-work"]["resources"])
        self.assertIn("references/deck-playbook.md", skills["presentation-work"]["resources"])


class ReadSkillToolTests(IsolatedAsyncioTestCase):
    async def test_read_skill_returns_full_instructions_for_enabled_skill(self) -> None:
        result = await read_skill("codebase-engineering")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["metadata"]["skill_id"], "codebase-engineering")
        self.assertIn("Read the code first", result["metadata"]["instructions"])

    async def test_read_skill_rejects_disabled_skill(self) -> None:
        settings = {"agentSkills": {"disabledDefaults": ["codebase-engineering"]}}
        repo = AsyncMock()
        repo.get_user_settings.return_value = settings

        with patch("nexus.tools.skills.get_history_repository", return_value=repo), patch(
            "nexus.tools.skills.get_owner_id",
            return_value="user-1",
        ):
            result = await read_skill("codebase-engineering")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "SKILL_DISABLED")
        self.assertEqual(result["metadata"]["skill_id"], "codebase-engineering")

    async def test_read_skill_file_returns_bundled_resource(self) -> None:
        result = await read_skill_file("document-work", "references/deliverable-checklist.md")
        self.assertEqual(result["status"], "success")
        self.assertIn("Filename is specific", result["metadata"]["content"])

    async def test_read_skill_file_rejects_path_traversal(self) -> None:
        result = await read_skill_file("document-work", "../secrets.txt")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "INVALID_SKILL_PATH")
