# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared document design tokens and slide normalization.

Visual rendering for PPTX lives in ``document_templates/pptx_dark.py`` so the
sandbox can run it without importing nexus. Host-side tools normalize content
here, then hand the sandbox a JSON payload plus that renderer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SLIDE_LAYOUTS = frozenset({"title", "section", "content", "split", "stats", "quote", "closing"})
PPTX_GENERATOR_PATH = Path(__file__).resolve().parent / "document_templates" / "pptx_dark.py"

# Modern dark: near-black field, one teal accent, stone neutrals.
THEME = {
    "bg": "#0B0B0E",
    "surface": "#16161C",
    "text": "#F5F5F4",
    "muted": "#A8A29E",
    "accent": "#2DD4BF",
    "rule": "#292524",
}

PDF_REPORT_CSS = """
@page {
    size: A4;
    margin: 2.2cm 1.8cm 2.4cm 1.8cm;
    @bottom-center {
        content: counter(page);
        font-size: 9pt;
        color: #78716c;
        font-family: 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif;
        letter-spacing: 0.08em;
    }
}
html, body {
    margin: 0;
    padding: 0;
}
body {
    font-family: 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.65;
    color: #1c1917;
}
.cover {
    background: #0B0B0E;
    color: #F5F5F4;
    padding: 42px 36px 32px;
    margin: -2.2cm -1.8cm 28px -1.8cm;
}
.cover .kicker {
    font-size: 10pt;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #2DD4BF;
    margin: 0 0 14px;
}
.cover h1 {
    font-size: 26pt;
    line-height: 1.15;
    letter-spacing: -0.03em;
    color: #F5F5F4;
    border: none;
    padding: 0;
    margin: 0;
}
h1 {
    font-size: 20pt;
    color: #0c0a09;
    letter-spacing: -0.02em;
    border-bottom: 2px solid #2DD4BF;
    padding-bottom: 8px;
    margin: 8px 0 16px;
}
h2 {
    font-size: 14.5pt;
    color: #1c1917;
    border-bottom: 1px solid #e7e5e4;
    padding-bottom: 4px;
    margin-top: 26px;
}
h3 { font-size: 12.5pt; color: #44403c; margin-top: 18px; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 14px 0;
}
th, td {
    border: 1px solid #e7e5e4;
    padding: 8px 10px;
    text-align: left;
    font-size: 10pt;
}
th {
    background-color: #0B0B0E;
    color: #F5F5F4;
    font-weight: 600;
}
tr:nth-child(even) td { background: #fafaf9; }
code {
    background-color: #f5f5f4;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 9.5pt;
}
pre {
    background-color: #0B0B0E;
    color: #e7e5e4;
    padding: 14px 16px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 9.5pt;
    line-height: 1.45;
}
blockquote {
    border-left: 3px solid #2DD4BF;
    margin: 14px 0;
    padding: 6px 16px;
    color: #57534e;
}
ul, ol { padding-left: 22px; }
li { margin-bottom: 5px; }
"""


def pptx_generator_source() -> str:
    return PPTX_GENERATOR_PATH.read_text(encoding="utf-8")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _stats_list(value: Any) -> list[dict[str, str]]:
    stats: list[dict[str, str]] = []
    if not isinstance(value, list):
        return stats
    for item in value:
        if isinstance(item, dict):
            number = str(item.get("value") or item.get("number") or item.get("stat") or "").strip()
            label = str(item.get("label") or item.get("caption") or item.get("name") or "").strip()
        elif isinstance(item, (list, tuple)) and item:
            number = str(item[0]).strip()
            label = str(item[1]).strip() if len(item) > 1 else ""
        else:
            continue
        if number or label:
            stats.append({"value": number or "—", "label": label or "Metric"})
    return stats[:4]


def _infer_layout(item: dict[str, Any], index: int, total: int) -> str:
    explicit = str(item.get("layout") or item.get("type") or item.get("kind") or "").strip().lower()
    if explicit in SLIDE_LAYOUTS:
        return explicit
    if _stats_list(item.get("stats") or item.get("kpis") or item.get("metrics")):
        return "stats"
    if str(item.get("quote") or "").strip():
        return "quote"
    if _string_list(item.get("left") or item.get("left_bullets")) or _string_list(
        item.get("right") or item.get("right_bullets")
    ):
        return "split"
    bullets = _string_list(item.get("bullets") or item.get("points") or item.get("body"))
    title = str(item.get("title") or item.get("heading") or "").strip().lower()
    subtitle = str(item.get("subtitle") or item.get("dek") or "").strip()
    closing_marks = ("thank", "questions", "next step", "next steps", "let's go", "closing")
    if index == total - 1 and any(mark in title for mark in closing_marks):
        return "closing"
    if index == 0 and not bullets:
        return "title"
    if not bullets and subtitle and index == 0:
        return "title"
    return "content"


def normalize_slides(slides: list[Any] | None, *, deck_title: str = "") -> list[dict[str, Any]]:
    raw_items = [item for item in (slides or [])]
    total = len(raw_items)
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, str):
            title = item.strip()
            if not title:
                continue
            layout = "title" if index == 0 and total == 1 else "content"
            normalized.append({
                "layout": layout,
                "kicker": "",
                "title": title,
                "subtitle": deck_title if layout == "title" else "",
                "bullets": [],
                "left": [],
                "right": [],
                "stats": [],
                "quote": "",
                "attribution": "",
                "footnote": "",
            })
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("heading") or "").strip()
        bullets = _string_list(item.get("bullets") or item.get("points") or item.get("body"))
        left = _string_list(item.get("left") or item.get("left_bullets") or item.get("col1"))
        right = _string_list(item.get("right") or item.get("right_bullets") or item.get("col2"))
        stats = _stats_list(item.get("stats") or item.get("kpis") or item.get("metrics"))
        quote = str(item.get("quote") or "").strip()
        if not title and bullets:
            title = bullets[0]
            bullets = bullets[1:]
        if not (title or bullets or left or right or stats or quote):
            continue
        layout = _infer_layout(item, index, total)
        normalized.append({
            "layout": layout,
            "kicker": str(item.get("kicker") or item.get("eyebrow") or item.get("label") or "").strip(),
            "title": title or ("Slide" if layout != "quote" else ""),
            "subtitle": str(item.get("subtitle") or item.get("dek") or item.get("description") or "").strip(),
            "bullets": bullets,
            "left": left,
            "right": right,
            "stats": stats,
            "quote": quote,
            "attribution": str(item.get("attribution") or item.get("cite") or item.get("author") or "").strip(),
            "footnote": str(item.get("footnote") or item.get("footer") or "").strip(),
        })
    return normalized
