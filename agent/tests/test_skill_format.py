# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.skill_format import SkillFormatError, parse_skill_md, render_skill_md, safe_skill_relpath
from nexus.skills import list_agent_skills, skill_from_parsed


SAMPLE_MD = """---
name: pdf-processing
description: Extract text from PDFs and fill forms. Use when the user mentions PDFs.
license: Apache-2.0
metadata:
  cocomputer.category: Documents
  cocomputer.trigger: Use when handling PDF files.
---

# PDF processing

1. Confirm the file path.
2. Extract text before summarizing.
"""


class SkillFormatTests(TestCase):
    def test_parse_roundtrip(self) -> None:
        parsed = parse_skill_md(SAMPLE_MD)
        self.assertEqual(parsed.name, "pdf-processing")
        self.assertIn("PDFs", parsed.description)
        self.assertIn("Extract text", parsed.body)
        self.assertEqual(parsed.category, "Documents")
        rendered = render_skill_md(skill_from_parsed(parsed) or {})
        again = parse_skill_md(rendered)
        self.assertEqual(again.name, "pdf-processing")

    def test_parse_requires_description(self) -> None:
        with self.assertRaises(SkillFormatError):
            parse_skill_md("---\nname: x\n---\n\nbody\n")

    def test_safe_relpath_blocks_traversal(self) -> None:
        self.assertIsNone(safe_skill_relpath("../etc/passwd"))
        self.assertIsNone(safe_skill_relpath("/etc/passwd"))
        self.assertEqual(safe_skill_relpath("scripts/csv_preview.py"), "scripts/csv_preview.py")

    def test_imported_skill_overrides_builtin_id(self) -> None:
        parsed = parse_skill_md(SAMPLE_MD.replace("pdf-processing", "document-work", 1))
        imported = skill_from_parsed(parsed)
        assert imported is not None
        settings = {"agentSkills": {"custom": [imported]}}
        listed = list_agent_skills(settings)
        match = next(skill for skill in listed if skill["skill_id"] == "document-work")
        self.assertEqual(match["source"], "user")
        self.assertIn("Confirm the file path", match["instructions"])
