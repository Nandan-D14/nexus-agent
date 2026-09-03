# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.skill_catalog import (
    CatalogSourceError,
    CatalogSource,
    catalog_item_from_parsed,
    clear_catalog_cache,
    discover_skill_md_paths,
    github_blob_url,
    github_tree_api_url,
    is_source_available,
    load_catalog,
    parse_github_source,
    raw_skill_md_url,
    tree_paths_from_payload,
)
from nexus.skill_format import parse_skill_md


VALID_MD = """---
name: pdf-extract
description: Extract text from PDFs when the user mentions PDF files.
license: Apache-2.0
---

# PDF extract
"""

INVALID_MD = """---
name: Broken Skill
---

no description
"""


class SkillCatalogParseTests(TestCase):
    def test_parse_default_ids(self) -> None:
        anthropic = parse_github_source("anthropics")
        self.assertIsNotNone(anthropic)
        assert anthropic is not None
        self.assertEqual(anthropic.owner, "anthropics")
        self.assertEqual(anthropic.prefix, "skills")
        vercel = parse_github_source("vercel")
        assert vercel is not None
        self.assertEqual(vercel.repo, "agent-skills")

    def test_parse_owner_repo(self) -> None:
        source = parse_github_source("acme/skill-pack")
        assert source is not None
        self.assertEqual(source.owner, "acme")
        self.assertEqual(source.repo, "skill-pack")
        self.assertEqual(source.ref, "main")
        self.assertEqual(source.prefix, "")

    def test_parse_github_tree_url(self) -> None:
        source = parse_github_source("https://github.com/acme/skills/tree/develop/skills")
        assert source is not None
        self.assertEqual(source.ref, "develop")
        self.assertEqual(source.prefix, "skills")

    def test_rejects_ssrf_and_non_github(self) -> None:
        for value in (
            "http://github.com/acme/skills",
            "https://evil.com/anthropics/skills",
            "https://github.com.evil.com/acme/skills",
            "https://127.0.0.1/acme/skills",
            "https://localhost/acme/skills",
            "../etc/passwd",
            "acme",
        ):
            with self.subTest(value=value):
                with self.assertRaises(CatalogSourceError):
                    parse_github_source(value)

    def test_empty_source_is_defaults(self) -> None:
        self.assertIsNone(parse_github_source(""))
        self.assertIsNone(parse_github_source(None))

    def test_discover_skips_nested_without_skill_md_and_shadows(self) -> None:
        paths = discover_skill_md_paths(
            [
                "README.md",
                "skills/pdf/SKILL.md",
                "skills/pdf/scripts/extract.py",
                "skills/pdf/nested/SKILL.md",
                "skills/broken/notes.md",
                "skills/.github/SKILL.md",
                "template/SKILL.md",
                "SKILL.md",
            ],
            prefix="skills",
        )
        self.assertEqual(paths, ["skills/pdf/SKILL.md"])

    def test_discover_root_layout_and_depth(self) -> None:
        paths = discover_skill_md_paths(
            [
                "react-best-practices/SKILL.md",
                "deep/a/b/c/d/SKILL.md",
                "skills/web/SKILL.md",
            ]
        )
        self.assertIn("react-best-practices/SKILL.md", paths)
        self.assertIn("skills/web/SKILL.md", paths)
        self.assertNotIn("deep/a/b/c/d/SKILL.md", paths)

    def test_tree_paths_ignore_non_blobs(self) -> None:
        paths = tree_paths_from_payload(
            {
                "tree": [
                    {"path": "skills/pdf", "type": "tree"},
                    {"path": "skills/pdf/SKILL.md", "type": "blob"},
                ]
            }
        )
        self.assertEqual(paths, ["skills/pdf/SKILL.md"])

    def test_source_available_only_anthropic_docs(self) -> None:
        self.assertTrue(is_source_available("anthropics", "pdf"))
        self.assertFalse(is_source_available("anthropics", "pdf-extract"))
        self.assertFalse(is_source_available("vercel-labs", "pdf"))

    def test_catalog_item_urls(self) -> None:
        source = CatalogSource("anthropics", "skills", "main", "skills", "anthropics", "Anthropic")
        parsed = parse_skill_md(VALID_MD)
        item = catalog_item_from_parsed(parsed, source=source, path="skills/pdf-extract/SKILL.md")
        self.assertEqual(item["id"], "pdf-extract")
        self.assertEqual(
            item["source_url"],
            "https://github.com/anthropics/skills/blob/main/skills/pdf-extract/SKILL.md",
        )
        self.assertTrue(item["html_url"].endswith("/skills/pdf-extract"))
        self.assertEqual(
            github_tree_api_url(source),
            "https://api.github.com/repos/anthropics/skills/git/trees/main?recursive=1",
        )
        self.assertEqual(
            raw_skill_md_url(source, "skills/pdf-extract/SKILL.md"),
            "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf-extract/SKILL.md",
        )
        self.assertEqual(github_blob_url(source, "skills/pdf/SKILL.md").count("github.com"), 1)


class SkillCatalogLoadTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_catalog_cache()

    async def test_load_skips_invalid_skill_md(self) -> None:
        tree = {
            "tree": [
                {"path": "skills/pdf-extract/SKILL.md", "type": "blob"},
                {"path": "skills/broken/SKILL.md", "type": "blob"},
                {"path": "skills/missing/notes.md", "type": "blob"},
            ]
        }
        texts = {
            "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf-extract/SKILL.md": VALID_MD,
            "https://raw.githubusercontent.com/anthropics/skills/main/skills/broken/SKILL.md": INVALID_MD,
        }

        async def fetch_json(_url: str) -> object:
            return tree

        async def fetch_text(url: str) -> str | None:
            return texts.get(url)

        catalog = await load_catalog(
            "anthropics",
            fetch_json=fetch_json,
            fetch_text=fetch_text,
            installed_ids={"pdf-extract"},
            use_cache=False,
        )
        ids = [item["id"] for item in catalog["skills"]]
        self.assertEqual(ids, ["pdf-extract"])
        self.assertTrue(catalog["skills"][0]["installed"])
        self.assertNotIn("broken", ids)

    async def test_defaults_merge_two_sources(self) -> None:
        async def fetch_json(url: str) -> object:
            if "vercel-labs" in url:
                return {"tree": [{"path": "react-best-practices/SKILL.md", "type": "blob"}]}
            return {"tree": [{"path": "skills/pdf-extract/SKILL.md", "type": "blob"}]}

        async def fetch_text(url: str) -> str | None:
            if "react-best-practices" in url:
                return VALID_MD.replace("pdf-extract", "react-best-practices", 1)
            return VALID_MD

        catalog = await load_catalog(
            None,
            fetch_json=fetch_json,
            fetch_text=fetch_text,
            use_cache=False,
        )
        ids = {item["id"] for item in catalog["skills"]}
        self.assertEqual(ids, {"pdf-extract", "react-best-practices"})
        self.assertEqual(len(catalog["sources"]), 2)

    async def test_load_catalog_rejects_ssrf_without_fetch(self) -> None:
        async def fetch_json(_url: str) -> object:
            self.fail("must not fetch GitHub for a rejected source")
            return {}

        async def fetch_text(_url: str) -> str | None:
            self.fail("must not fetch SKILL.md for a rejected source")
            return None

        with self.assertRaises(CatalogSourceError):
            await load_catalog(
                "https://127.0.0.1/acme/skills",
                fetch_json=fetch_json,
                fetch_text=fetch_text,
                use_cache=False,
            )
