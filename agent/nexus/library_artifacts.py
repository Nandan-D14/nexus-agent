# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Classify durable artifacts for the cross-session Library page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

LibraryCategory = Literal[
    "slides",
    "documents",
    "spreadsheets",
    "images",
    "media",
    "others",
]

LIBRARY_CATEGORIES: frozenset[str] = frozenset(
    {"slides", "documents", "spreadsheets", "images", "media", "others"}
)

SOURCE_KINDS = frozenset(
    {
        "summary",
        "screenshot_reference",
        "export_reference",
        "workspace_output",
    }
)

SOURCE_TOOLS = frozenset(
    {
        "scrape_web_page",
        "web_search",
        "tavily_search",
    }
)

_SLIDE_EXTENSIONS = (".pptx", ".ppt")
_SHEET_EXTENSIONS = (".xlsx", ".xls", ".csv")
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp")
_MEDIA_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".mp4", ".mov", ".webm", ".mkv")
_DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt")


@dataclass(frozen=True)
class LibraryListRow:
    artifact: Any
    session_title: str
    category: LibraryCategory


def _metadata(artifact: Any) -> dict[str, Any]:
    metadata = getattr(artifact, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _kind(artifact: Any) -> str:
    value = getattr(artifact, "kind", "")
    return value.lower() if isinstance(value, str) else ""


def _normalized_path(artifact: Any) -> str:
    path = getattr(artifact, "path", None)
    if not isinstance(path, str):
        return ""
    return path.replace("\\", "/").strip()


def _filename(artifact: Any) -> str:
    path = _normalized_path(artifact)
    if path:
        name = path.rsplit("/", 1)[-1]
        if name:
            return name.lower()
    title = getattr(artifact, "title", "")
    return title.lower() if isinstance(title, str) else ""


def _content_type(artifact: Any) -> str:
    value = _metadata(artifact).get("content_type")
    return value.lower() if isinstance(value, str) else ""


def is_library_artifact(artifact: Any) -> bool:
    """Return False for scrapes, search dumps, and other working sources."""
    metadata = _metadata(artifact)
    tool = metadata.get("tool")
    if isinstance(tool, str) and tool in SOURCE_TOOLS:
        return False
    role = metadata.get("role")
    if role == "source":
        return False
    if _kind(artifact) in SOURCE_KINDS:
        return False
    path = _normalized_path(artifact)
    if path.startswith("sources/"):
        return False
    return True


def library_category(artifact: Any) -> LibraryCategory:
    """Map an artifact to a Library filter bucket (never 'websites')."""
    kind = _kind(artifact)
    content_type = _content_type(artifact)
    filename = _filename(artifact)

    if (
        kind == "presentation"
        or "presentationml" in content_type
        or "ms-powerpoint" in content_type
        or filename.endswith(_SLIDE_EXTENSIONS)
    ):
        return "slides"

    if (
        kind in {"spreadsheet", "csv"}
        or "spreadsheetml" in content_type
        or "ms-excel" in content_type
        or filename.endswith(_SHEET_EXTENSIONS)
    ):
        return "spreadsheets"

    if (
        kind in {"image", "screenshot"}
        or content_type.startswith("image/")
        or filename.endswith(_IMAGE_EXTENSIONS)
    ):
        return "images"

    if (
        kind in {"audio", "video"}
        or content_type.startswith(("audio/", "video/"))
        or filename.endswith(_MEDIA_EXTENSIONS)
    ):
        return "media"

    if (
        kind in {"document", "pdf", "pdf_report"}
        or "pdf" in content_type
        or "wordprocessingml" in content_type
        or "msword" in content_type
        or filename.endswith(_DOC_EXTENSIONS)
    ):
        return "documents"

    return "others"


def matches_library_search(artifact: Any, session_title: str, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    title = getattr(artifact, "title", "")
    preview = getattr(artifact, "preview", "")
    haystacks = (
        title if isinstance(title, str) else "",
        preview if isinstance(preview, str) else "",
        session_title or "",
        _filename(artifact),
    )
    return any(needle in value.lower() for value in haystacks)
