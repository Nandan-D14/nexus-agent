# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Optional Agent Skills resources bundled with built-in playbooks."""

from __future__ import annotations

BUNDLED_SKILL_FILES: dict[str, dict[str, str]] = {
    "document-work": {
        "references/deliverable-checklist.md": """# Document deliverable checklist

- Filename is specific (`q3-board-update.pdf`, not `document.pdf`).
- Title, date, and audience are in the first screen of content.
- Markdown draft exists before PDF/DOCX conversion.
- Generated file was opened or extracted to confirm it is not empty.
- Final file was saved with save_as_artifact (or left in outputs/ with a clear path).
""",
    },
    "spreadsheet-work": {
        "references/sheet-checklist.md": """# Spreadsheet deliverable checklist

- Header row is human-readable and unique.
- Units and currency are explicit in column names or a notes sheet.
- Totals/formulas are described; do not invent calculated values without showing the method.
- CSV previewed before a wide XLSX export when the source is tabular text.
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
