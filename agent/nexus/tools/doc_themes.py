# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Design themes shared by the PPTX, DOCX, XLSX, and PDF generators.

Each theme is plain JSON-serialisable data so it can be handed straight to the
sandbox renderer scripts. Colors are uppercase RRGGBB without a leading '#'
because that is the form python-pptx, python-docx, and openpyxl all expect.

Office font names must be fonts that ship with Word/PowerPoint so the file
still looks right on the recipient's machine. The ``css_*`` stacks are used by
WeasyPrint inside the sandbox, where only the DejaVu/Liberation families are
guaranteed to exist.
"""

from __future__ import annotations

from typing import Any

_SANS = "'DejaVu Sans', 'Liberation Sans', Arial, sans-serif"
_SERIF = "'DejaVu Serif', 'Liberation Serif', Georgia, serif"
_MONO = "'DejaVu Sans Mono', 'Liberation Mono', 'Courier New', monospace"


DOCUMENT_THEMES: dict[str, dict[str, Any]] = {
    "aurora": {
        "name": "Aurora",
        "summary": "Clean modern light deck with an indigo accent. Safe default for most audiences.",
        "background": "FFFFFF",
        "surface": "F4F6FE",
        "surface_alt": "EAEEFC",
        "ink": "0F172A",
        "muted": "64748B",
        "hairline": "DDE3F0",
        "accent": "4F46E5",
        "accent_soft": "E5E8FD",
        "accent_alt": "0EA5E9",
        "cover_background": "1E1B4B",
        "cover_ink": "FFFFFF",
        "cover_muted": "C7D2FE",
        "cover_accent": "A5B4FC",
        "chart_palette": ["4F46E5", "0EA5E9", "8B5CF6", "22C55E", "F59E0B", "EF4444"],
        "fonts": {
            "heading": "Segoe UI",
            "body": "Segoe UI",
            "mono": "Consolas",
            "css_heading": _SANS,
            "css_body": _SANS,
            "css_mono": _MONO,
        },
    },
    "midnight": {
        "name": "Midnight",
        "summary": "Dark, high-contrast deck for product launches, demos, and on-stage talks.",
        "background": "0B1220",
        "surface": "141F33",
        "surface_alt": "1C2942",
        "ink": "F8FAFC",
        "muted": "94A3B8",
        "hairline": "24344F",
        "accent": "38BDF8",
        "accent_soft": "16324B",
        "accent_alt": "A78BFA",
        "cover_background": "05090F",
        "cover_ink": "FFFFFF",
        "cover_muted": "94A3B8",
        "cover_accent": "38BDF8",
        "chart_palette": ["38BDF8", "A78BFA", "34D399", "FBBF24", "F472B6", "60A5FA"],
        "fonts": {
            "heading": "Segoe UI",
            "body": "Segoe UI",
            "mono": "Consolas",
            "css_heading": _SANS,
            "css_body": _SANS,
            "css_mono": _MONO,
        },
    },
    "executive": {
        "name": "Executive",
        "summary": "Navy and gold with serif headings. Board decks, financials, and formal reports.",
        "background": "FFFFFF",
        "surface": "F2F5F9",
        "surface_alt": "E4EBF3",
        "ink": "12233B",
        "muted": "5A6B80",
        "hairline": "D4DEEA",
        "accent": "0B3D69",
        "accent_soft": "E1EAF4",
        "accent_alt": "C9A227",
        "cover_background": "0B3D69",
        "cover_ink": "FFFFFF",
        "cover_muted": "BFD2E4",
        "cover_accent": "C9A227",
        "chart_palette": ["0B3D69", "C9A227", "3E7CB1", "7A8FA6", "2E7D32", "9C3D3D"],
        "fonts": {
            "heading": "Georgia",
            "body": "Calibri",
            "mono": "Consolas",
            "css_heading": _SERIF,
            "css_body": _SANS,
            "css_mono": _MONO,
        },
    },
    "sunrise": {
        "name": "Sunrise",
        "summary": "Warm coral and amber. Marketing, brand, and customer-facing storytelling.",
        "background": "FFFDFB",
        "surface": "FFF3EA",
        "surface_alt": "FDE7D8",
        "ink": "2B1B12",
        "muted": "8A6F5F",
        "hairline": "F0DCCD",
        "accent": "E4572E",
        "accent_soft": "FCE3D8",
        "accent_alt": "F4A620",
        "cover_background": "2B1B12",
        "cover_ink": "FFF7F1",
        "cover_muted": "D8BCA9",
        "cover_accent": "F4A620",
        "chart_palette": ["E4572E", "F4A620", "17BEBB", "76B041", "8367C7", "D64550"],
        "fonts": {
            "heading": "Segoe UI",
            "body": "Segoe UI",
            "mono": "Consolas",
            "css_heading": _SANS,
            "css_body": _SANS,
            "css_mono": _MONO,
        },
    },
    "forest": {
        "name": "Forest",
        "summary": "Calm green and slate. Sustainability, research, and operations reviews.",
        "background": "FFFFFF",
        "surface": "F0F6F2",
        "surface_alt": "DFEDE5",
        "ink": "12211A",
        "muted": "5C7267",
        "hairline": "D3E3D9",
        "accent": "1F7A5C",
        "accent_soft": "DCEDE5",
        "accent_alt": "8CB369",
        "cover_background": "10241C",
        "cover_ink": "F2FBF7",
        "cover_muted": "A9C7B8",
        "cover_accent": "6FD3A8",
        "chart_palette": ["1F7A5C", "8CB369", "4C86A8", "D9A404", "B5533C", "6B4E9B"],
        "fonts": {
            "heading": "Segoe UI",
            "body": "Segoe UI",
            "mono": "Consolas",
            "css_heading": _SANS,
            "css_body": _SANS,
            "css_mono": _MONO,
        },
    },
    "mono": {
        "name": "Mono",
        "summary": "Minimal editorial black and white. Whitepapers, essays, and print-first output.",
        "background": "FFFFFF",
        "surface": "F4F4F5",
        "surface_alt": "E7E7EA",
        "ink": "111111",
        "muted": "6B7280",
        "hairline": "DEDEE2",
        "accent": "111111",
        "accent_soft": "E4E4E7",
        "accent_alt": "6B7280",
        "cover_background": "111111",
        "cover_ink": "FFFFFF",
        "cover_muted": "A1A1AA",
        "cover_accent": "FFFFFF",
        "chart_palette": ["111111", "6B7280", "9CA3AF", "3F3F46", "52525B", "D4D4D8"],
        "fonts": {
            "heading": "Georgia",
            "body": "Calibri",
            "mono": "Consolas",
            "css_heading": _SERIF,
            "css_body": _SANS,
            "css_mono": _MONO,
        },
    },
}

DEFAULT_THEME = "aurora"

THEME_CHOICES = tuple(DOCUMENT_THEMES)

#: One-line catalog suitable for embedding in tool docstrings and skill prompts.
THEME_HELP = " | ".join(
    f"{key}: {value['summary']}" for key, value in DOCUMENT_THEMES.items()
)


def _normalize_hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lstrip("#").upper()
    if len(text) == 3 and all(ch in "0123456789ABCDEF" for ch in text):
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789ABCDEF" for ch in text):
        return fallback
    return text


def resolve_theme(name: str | None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a full theme dict for ``name``, applying optional color overrides.

    Unknown names fall back to the default theme rather than erroring, so a
    model hallucinating a theme id still produces a good-looking document.
    """
    key = str(name or "").strip().lower().replace(" ", "-")
    base = DOCUMENT_THEMES.get(key) or DOCUMENT_THEMES[DEFAULT_THEME]
    theme: dict[str, Any] = {
        **base,
        "id": key if key in DOCUMENT_THEMES else DEFAULT_THEME,
        "fonts": dict(base["fonts"]),
        "chart_palette": list(base["chart_palette"]),
    }

    if not overrides:
        return theme

    for field in (
        "background",
        "surface",
        "surface_alt",
        "ink",
        "muted",
        "hairline",
        "accent",
        "accent_soft",
        "accent_alt",
        "cover_background",
        "cover_ink",
        "cover_muted",
        "cover_accent",
    ):
        if field in overrides:
            theme[field] = _normalize_hex(overrides[field], theme[field])

    palette = overrides.get("chart_palette")
    if isinstance(palette, list) and palette:
        theme["chart_palette"] = [
            _normalize_hex(entry, theme["chart_palette"][idx % len(theme["chart_palette"])])
            for idx, entry in enumerate(palette)
        ]

    fonts = overrides.get("fonts")
    if isinstance(fonts, dict):
        for field in ("heading", "body", "mono", "css_heading", "css_body", "css_mono"):
            value = str(fonts.get(field) or "").strip()
            if value:
                theme["fonts"][field] = value

    return theme
