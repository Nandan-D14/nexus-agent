# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import base64
import io
import sys
import zipfile
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.models import AgentSkillImportRequest
from nexus.skill_format import parse_skill_md
from nexus.skill_import import (
    companion_urls_for_skill,
    decode_zip_b64,
    files_from_github_contents,
    github_contents_api_url,
    referenced_skill_paths,
    unpack_skill_zip,
)
from nexus.skill_runtime import sync_skills_to_sandbox
from nexus.skills import list_agent_skills, skill_from_parsed


SAMPLE_MD = """---
name: pdf-extract
description: Extract text from PDFs. Use when the user mentions PDF files.
metadata:
  cocomputer.category: Documents
---

# PDF extract

Run `scripts/extract.py` then read `references/notes.md`.
"""


class FakeSandbox:
    is_alive = True

    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.dirs: list[str] = []

    def ensure_directory(self, path: str) -> None:
        self.dirs.append(path)

    def write_text_file(self, path: str, content: str, append: bool = False) -> None:
        self.files[path] = (self.files.get(path, "") + content) if append else content


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class SkillImportTests(TestCase):
    def test_unpack_zip_strips_folder_prefix(self) -> None:
        data = _zip_bytes(
            {
                "pdf-extract/SKILL.md": SAMPLE_MD,
                "pdf-extract/scripts/extract.py": "print('ok')\n",
                "pdf-extract/references/notes.md": "# notes\n",
            }
        )
        skill_md, files = unpack_skill_zip(data)
        self.assertIn("Extract text", skill_md)
        self.assertEqual(files["scripts/extract.py"], "print('ok')\n")
        self.assertEqual(files["references/notes.md"], "# notes\n")

    def test_unpack_zip_skips_path_traversal(self) -> None:
        data = _zip_bytes(
            {
                "SKILL.md": SAMPLE_MD,
                "../secrets.txt": "nope",
                "scripts/ok.py": "x = 1\n",
            }
        )
        _skill_md, files = unpack_skill_zip(data)
        self.assertNotIn("../secrets.txt", files)
        self.assertEqual(files["scripts/ok.py"], "x = 1\n")

    def test_referenced_paths_and_companion_urls(self) -> None:
        paths = referenced_skill_paths(SAMPLE_MD)
        self.assertEqual(paths, ["scripts/extract.py", "references/notes.md"])
        pairs = companion_urls_for_skill(
            "https://raw.githubusercontent.com/acme/skills/main/pdf-extract/SKILL.md",
            SAMPLE_MD,
        )
        self.assertEqual(
            pairs[0],
            (
                "scripts/extract.py",
                "https://raw.githubusercontent.com/acme/skills/main/pdf-extract/scripts/extract.py",
            ),
        )

    def test_github_contents_api_url_from_blob(self) -> None:
        url = github_contents_api_url(
            "https://github.com/acme/skills/blob/main/pdf-extract/SKILL.md"
        )
        self.assertEqual(
            url,
            "https://api.github.com/repos/acme/skills/contents/pdf-extract?ref=main",
        )

    def test_github_contents_files_use_prefix(self) -> None:
        files = files_from_github_contents(
            [
                {
                    "type": "file",
                    "name": "extract.py",
                    "download_url": "https://raw.githubusercontent.com/acme/skills/main/pdf-extract/scripts/extract.py",
                }
            ],
            prefix="scripts",
        )
        self.assertEqual(files[0][0], "scripts/extract.py")

    def test_import_request_accepts_legacy_field_names(self) -> None:
        payload = AgentSkillImportRequest.model_validate(
            {"skill_md": SAMPLE_MD, "source_url": "https://example.com/SKILL.md"}
        )
        self.assertIn("Extract text", payload.skill_md or "")
        self.assertTrue(payload.source_url)

    def test_zip_b64_roundtrip_to_skill(self) -> None:
        raw = _zip_bytes({"SKILL.md": SAMPLE_MD, "scripts/extract.py": "print(1)\n"})
        md, files = unpack_skill_zip(decode_zip_b64(base64.b64encode(raw).decode("ascii")))
        parsed = parse_skill_md(md)
        skill = skill_from_parsed(parsed, files=files)
        assert skill is not None
        self.assertEqual(skill["skill_id"], "pdf-extract")
        self.assertIn("scripts/extract.py", skill["files"])

    def test_sync_writes_skill_md_and_resources(self) -> None:
        sandbox = FakeSandbox()
        parsed = parse_skill_md(SAMPLE_MD)
        imported = skill_from_parsed(parsed, files={"scripts/extract.py": "print(1)\n"})
        disabled = {skill["skill_id"] for skill in list_agent_skills(None)}
        settings = {
            "agentSkills": {
                "custom": [imported],
                "disabledDefaults": sorted(disabled),
            }
        }
        written = sync_skills_to_sandbox(sandbox, settings)
        self.assertGreaterEqual(written, 2)
        skill_root = next(path for path in sandbox.dirs if path.endswith("pdf-extract"))
        self.assertIn(f"{skill_root}/SKILL.md", sandbox.files)
        self.assertIn(f"{skill_root}/scripts/extract.py", sandbox.files)
