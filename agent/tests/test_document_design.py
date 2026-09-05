# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.document_design import normalize_slides, pptx_generator_source
from nexus.google_drive import spreadsheet_csv_bytes
from nexus.tools.integrations import create_drive_sheet


class SlideNormalizationTests(TestCase):
    def test_legacy_title_and_bullets_become_content(self) -> None:
        slides = normalize_slides(
            [{"title": "Agenda", "bullets": ["Goals", "Timeline"]}],
            deck_title="Review",
        )
        self.assertEqual(len(slides), 1)
        self.assertEqual(slides[0]["layout"], "content")
        self.assertEqual(slides[0]["bullets"], ["Goals", "Timeline"])

    def test_first_slide_without_bullets_is_title(self) -> None:
        slides = normalize_slides(
            [{"title": "Q3 Review", "subtitle": "Finance offsite"}],
            deck_title="Q3 Review",
        )
        self.assertEqual(slides[0]["layout"], "title")
        self.assertEqual(slides[0]["subtitle"], "Finance offsite")

    def test_stats_and_split_and_quote_layouts(self) -> None:
        slides = normalize_slides(
            [
                {"title": "Impact", "stats": [{"value": "38%", "label": "Faster"}]},
                {"title": "Now vs next", "left": ["Manual"], "right": ["Automated"]},
                {"quote": "Ship the boring path first.", "attribution": "Eng"},
            ]
        )
        self.assertEqual([item["layout"] for item in slides], ["stats", "split", "quote"])

    def test_pptx_generator_source_is_valid_python(self) -> None:
        source = pptx_generator_source()
        compile(source, "pptx_dark.py", "exec")
        self.assertIn("2DD4BF", source)
        self.assertIn("modern-dark", source)
        self.assertIn("layout-title", source)

    def test_bootstrap_must_not_be_prepended_to_pptx_generator(self) -> None:
        from nexus.tools.docs import _SANDBOX_DEPS_BOOTSTRAP

        concatenated = (
            _SANDBOX_DEPS_BOOTSTRAP
            + "\nDATA_PATH = 'x'\nOUT_PATH = 'y'\nHTML_PATH = 'z'\n"
            + pptx_generator_source()
        )
        with self.assertRaisesRegex(SyntaxError, "from __future__"):
            compile(concatenated, "<concatenated>", "exec")


class SpreadsheetCsvTests(TestCase):
    def test_csv_includes_headers_and_rows(self) -> None:
        payload = spreadsheet_csv_bytes(["City", "Count"], [["Bengaluru", 3], ["Pune", None]])
        text = payload.decode("utf-8-sig")
        self.assertIn("City,Count", text)
        self.assertIn("Bengaluru,3", text)
        self.assertIn("Pune,", text)


class CreateDriveSheetTests(IsolatedAsyncioTestCase):
    async def test_requires_drive_connection(self) -> None:
        with patch(
            "nexus.tools.integrations.get_google_drive_client_from_context",
            new=AsyncMock(return_value=None),
        ):
            result = await create_drive_sheet(title="Hackathons", headers=["Name"], rows=[["A"]])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "AUTH_REQUIRED")

    async def test_creates_sheet_when_connected(self) -> None:
        client = AsyncMock()
        client.create_google_sheet.return_value = {
            "id": "sheet-1",
            "webViewLink": "https://docs.google.com/spreadsheets/d/sheet-1",
        }
        with patch(
            "nexus.tools.integrations.get_google_drive_client_from_context",
            new=AsyncMock(return_value=client),
        ):
            result = await create_drive_sheet(
                title="Hackathons",
                headers=["Name", "City"],
                rows=[["H1", "Bengaluru"]],
            )
        self.assertEqual(result["status"], "success")
        client.create_google_sheet.assert_awaited_once()
        kwargs = client.create_google_sheet.await_args.kwargs
        self.assertEqual(kwargs["title"], "Hackathons")
        self.assertEqual(kwargs["headers"], ["Name", "City"])
