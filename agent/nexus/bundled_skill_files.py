# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Optional Agent Skills resources bundled with built-in playbooks."""

from __future__ import annotations

BUNDLED_SKILL_FILES: dict[str, dict[str, str]] = {
    "document-work": {
        "references/deliverable-checklist.md": """# Document deliverable checklist

- Filename is specific (`q3-board-update.pdf`, not `document.pdf`).
- Title, date, and audience are in the first screen of content.
- Markdown uses H2 sections, short paragraphs, and tables for comparisons.
- Opening section states the takeaway in 2-3 sentences.
- Generated file was opened or extracted to confirm it is not empty.
- Final file was saved with save_as_artifact (or left in outputs/ with a clear path).
- Google Doc only when Drive is connected and the user asked for Docs; otherwise PDF/DOCX.
""",
    },
    "presentation-work": {
        "references/deck-playbook.md": """# Deck playbook

The renderer is modern dark: near-black field, Calibri, one teal accent.
Do not pick colors, fonts, or coordinates. Pick layouts and write copy.

## Structure
1. Title slide — kicker (audience or date), short title, one-line subtitle.
2. Section slides — one per chapter ("The problem", "The plan").
3. Content / split / stats / quote — the argument.
4. Closing — next steps or ask, not a wall of recap.

Target 6-12 slides. Cut anything that does not change the decision.

## Layouts
- `title` — cover. Title under 8 words.
- `section` — chapter break. Title only, optional subtitle.
- `content` — 3-5 bullets, each under 12 words. No paragraphs.
- `split` — two columns (`left`, `right`) for contrast (now/next, problem/fix).
- `stats` — 2-4 `{value, label}` tiles. Values first (`$4.2M`, `38%`).
- `quote` — one sentence + attribution.
- `closing` — thank-you / ask + up to 3 next-step bullets.

## Writing
- Headlines say the point, not the topic. "Costs drop 18% in Q2" not "Cost analysis".
- One idea per slide. If you need "also", split the slide.
- Numbers beat adjectives. Name the source in a footnote when it matters.
- Never put a full paragraph on a slide.

## Tool
Call `generate_pptx_report(title, slides=[...], filename)`.
Legacy `{title, bullets}` still works and gets the dark theme plus a cover slide.
""",
    },
    "spreadsheet-work": {
        "references/sheet-checklist.md": """# Spreadsheet deliverable checklist

- Header row is human-readable and unique.
- Units and currency are explicit in column names or a notes sheet.
- Totals/formulas are described; do not invent calculated values without showing the method.
- CSV previewed before a wide XLSX export when the source is tabular text.
- Google Sheet: `create_drive_sheet` when Drive is connected and the user asked for Sheets.
- Local workbook: `generate_excel_report` for .xlsx (freeze header, filter, numeric cells).
""",
        "scripts/csv_preview.py": '''#!/usr/bin/env python3
"""Print a CSV header plus the first N data rows. Usage: python csv_preview.py <file> [n]"""
from __future__ import annotations

import csv
import sys

path = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 8
with open(path, newline="", encoding="utf-8-sig") as handle:
    rows = list(csv.reader(handle))
if not rows:
    print("# empty file")
    raise SystemExit(0)
for row in rows[: limit + 1]:
    print(",".join(row))
print(f"# {max(0, len(rows) - 1)} data rows")
''',
    },
    "github-review": {
        "references/review-checklist.md": """# PR review checklist

- Summarize what changed and why before listing comments.
- Flag correctness, security, missing tests, and user-visible regressions first.
- Quote the file and region you are talking about.
- Separate blocking issues from nits.
- If the GitHub connector is available, prefer github_summarize_pr / github_read_file over guessing.
""",
    },
}
