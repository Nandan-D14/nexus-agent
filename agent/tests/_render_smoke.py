# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Local-only harness that runs the sandbox renderer scripts for real.

Not part of the unittest suite: it needs python-pptx/python-docx/openpyxl and
writes files to a temp dir. Run it with ``python tests/_render_smoke.py`` while
iterating on the renderers, then open the artifacts to eyeball the design.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from nexus.tools.doc_themes import DOCUMENT_THEMES, resolve_theme  # noqa: E402


def run(name: str, source: str, payload: dict, out_dir: pathlib.Path) -> dict:
    script = out_dir / f"{name}.py"
    data = out_dir / f"{name}.json"
    script.write_text(source, encoding="utf-8")
    data.write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), str(data)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        print(f"--- {name} FAILED ---")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        raise SystemExit(1)
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    if result.get("status") != "success":
        print(f"--- {name} returned error ---")
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    print(f"{name}: ok -> {result.get('path')} ({result.get('size')} bytes)")
    return result


DECK_SLIDES = [
    {
        "layout": "cover",
        "title": "Q3 Revenue Review",
        "subtitle": "Pipeline health, churn drivers, and the plan for Q4",
        "eyebrow": "Board Update",
        "meta": ["Finance Team", "September 2026"],
    },
    {"layout": "section", "title": "Where we landed", "body": "Headline numbers versus plan."},
    {
        "layout": "stats",
        "title": "Quarter at a glance",
        "stats": [
            {"value": "$4.2M", "label": "Net new ARR", "caption": "112% of plan, up 28% YoY"},
            {"value": "94%", "label": "Gross retention", "caption": "Best quarter on record"},
            {"value": "38", "label": "New logos", "caption": "Enterprise segment led growth"},
            {"value": "1.9x", "label": "Pipeline coverage", "caption": "Below the 3x target"},
        ],
        "bullets": ["Coverage is the one metric materially off plan."],
        "notes": "Lead with retention, then pivot to the coverage risk.",
    },
    {
        "layout": "chart",
        "title": "ARR by quarter",
        "chart": {
            "type": "bar",
            "categories": ["Q4 24", "Q1 25", "Q2 25", "Q3 25"],
            "series": [
                {"name": "New", "values": [2.1, 2.8, 3.4, 4.2]},
                {"name": "Expansion", "values": [1.2, 1.4, 1.1, 1.8]},
            ],
        },
        "bullets": [
            "Fourth consecutive quarter of **sequential growth**",
            "Expansion recovered after the Q2 dip",
            "  Driven by the usage-based tier",
        ],
    },
    {
        "layout": "columns",
        "title": "What worked and what did not",
        "columns": [
            {"heading": "Worked", "bullets": ["Usage-based pricing", "Partner sourced deals", "Faster security review"]},
            {"heading": "Did not", "bullets": ["Outbound in EMEA", "Self-serve conversion", "Onboarding time to value"]},
        ],
    },
    {
        "layout": "table",
        "title": "Segment detail",
        "table": {
            "headers": ["Segment", "ARR", "Growth", "Churn"],
            "rows": [
                ["Enterprise", "$2.4M", "+34%", "3.1%"],
                ["Mid-market", "$1.3M", "+18%", "6.4%"],
                ["SMB", "$0.5M", "-4%", "14.2%"],
            ],
        },
    },
    {
        "layout": "chart",
        "title": "Revenue mix",
        "chart": {
            "type": "doughnut",
            "categories": ["Enterprise", "Mid-market", "SMB"],
            "series": [{"name": "ARR", "values": [2.4, 1.3, 0.5]}],
        },
    },
    {
        "layout": "quote",
        "quote": "The product finally does the boring parts of my job, and it does them without me watching.",
        "attribution": "VP Operations, Fortune 500 logistics customer",
    },
    {
        "title": "Priorities for Q4",
        "bullets": [
            "Rebuild pipeline coverage to 3x by end of October",
            "Ship the onboarding revamp",
            "  Target: 7 days to first value",
            "  Owner: Platform team",
            "Fix SMB churn or sunset the tier",
        ],
    },
    {"layout": "closing", "title": "Questions?", "bullets": ["finance@example.com", "Deck and model in the shared drive"]},
]


REPORT_MD = """
# Executive summary

Revenue grew **28% year over year** to $4.2M, driven by the usage-based tier. The one
metric materially off plan is pipeline coverage at *1.9x* against a 3x target. See the
[pipeline model](https://example.com/model) for the underlying assumptions.

## Segment performance

| Segment    | ARR   | Growth | Churn |
|:-----------|------:|-------:|:-----:|
| Enterprise | $2.4M | +34%   | 3.1%  |
| Mid-market | $1.3M | +18%   | 6.4%  |
| SMB        | $0.5M | -4%    | 14.2% |

Enterprise carried the quarter. SMB contracted and now warrants a decision.

> Pipeline coverage below 2x in a quarter with rising win rates is a demand problem,
> not a conversion problem.

### What we shipped

- Usage-based pricing across all tiers
  - Rolled out to Enterprise first
  - Self-serve migration followed in week 6
- Partner-sourced deal registration
- Faster security review, now averaging 9 days

### What slipped

1. Outbound motion in EMEA
2. Self-serve conversion experiments
3. Onboarding time-to-value

---

## Reproducing these numbers

Run the extract against the warehouse:

```python
from finance import warehouse

arr = warehouse.query("select segment, sum(arr) from contracts group by 1")
print(arr.to_markdown())
```

Values are stored in cents; divide by `100` before formatting. Deprecated fields are
marked ~~legacy_arr~~ and should not be used.

## Recommendation

Rebuild coverage to 3x by end of October, ship the onboarding revamp, and either fix
SMB churn or sunset the tier.
"""


def main() -> None:
    out_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (
        pathlib.Path(tempfile.gettempdir()) / "cocomputer-render"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"output dir: {out_dir}\n")

    from nexus.tools.doc_render_pptx import PPTX_RENDERER

    for theme_id in DOCUMENT_THEMES:
        run(
            f"pptx_{theme_id}",
            PPTX_RENDERER,
            {
                "theme": resolve_theme(theme_id),
                "title": "Q3 Revenue Review",
                "subtitle": "Pipeline health, churn drivers, and the plan for Q4",
                "author": "Finance Team",
                "date": "September 2026",
                "slides": DECK_SLIDES,
                "out_path": str(out_dir / f"deck_{theme_id}.pptx"),
                "html_path": str(out_dir / f"deck_{theme_id}.html"),
                "workspace": str(out_dir),
                "auto_cover": True,
            },
            out_dir,
        )

    from nexus.tools.doc_render_docx import DOCX_RENDERER

    for theme_id in DOCUMENT_THEMES:
        run(
            f"docx_{theme_id}",
            DOCX_RENDERER,
            {
                "theme": resolve_theme(theme_id),
                "title": "Q3 Revenue Review",
                "subtitle": "Pipeline health, churn drivers, and the plan for Q4",
                "author": "Finance Team",
                "date": "September 2026",
                "markdown": REPORT_MD,
                "cover": True,
                "toc": True,
                "out_path": str(out_dir / f"report_{theme_id}.docx"),
                "workspace": str(out_dir),
            },
            out_dir,
        )

    print(f"\nAll renderers succeeded. Inspect: {out_dir}")


if __name__ == "__main__":
    main()
