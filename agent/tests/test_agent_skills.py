from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.skills import build_enabled_skills_prompt


class AgentSkillsPromptTests(TestCase):
    def test_prompt_tells_agent_to_select_matching_skills_before_tools(self) -> None:
        prompt = build_enabled_skills_prompt(None)

        self.assertIn("Before choosing an agent or tool, scan these skills", prompt)
        self.assertIn("apply every skill whose trigger matches", prompt)
        self.assertIn("not a connector by itself", prompt)
