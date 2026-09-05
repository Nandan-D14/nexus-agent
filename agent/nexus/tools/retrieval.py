# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Retrieval tool — keyword search over collected workspace sources.

Production stack Layer 1: instead of re-reading whole files into context,
the agent can query the material already collected under ``sources/`` (web
search dumps, scraped pages, uploaded documents) and get back only the
relevant chunks with file citations.

Deliberately dependency-free: tokenized keyword overlap scoring, no
embeddings. Good enough for "find the part of my sources that mentions X"
and easily replaceable by a vector index later.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from nexus.config import settings
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)

_CHUNK_CHARS = 900
_MAX_FILES = 40
_MAX_FILE_BYTES = 400_000
_TEXT_EXTENSIONS = (
    ".txt", ".md", ".json", ".csv", ".html", ".htm", ".xml",
    ".log", ".yaml", ".yml", ".py", ".js", ".ts",
)

_WORD_RE = re.compile(r"[a-z0-9]{2,}")

_STOPWORDS = frozenset(
    "the a an and or of to in for on with is are was were be been this that "
    "it its as at by from about into what which who how why when where".split()
)


def _tokenize(text: str) -> list[str]:
    return [
        word
        for word in _WORD_RE.findall(text.lower())
        if word not in _STOPWORDS
    ]


def _chunk_text(text: str) -> list[str]:
    """Split on paragraph boundaries, merging up to ~_CHUNK_CHARS per chunk."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > _CHUNK_CHARS:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
        while len(current) > _CHUNK_CHARS * 2:
            chunks.append(current[: _CHUNK_CHARS * 2])
            current = current[_CHUNK_CHARS * 2 :]
    if current:
        chunks.append(current)
    return chunks


def _score_chunk(query_terms: list[str], chunk: str) -> float:
    if not query_terms:
        return 0.0
    chunk_terms = set(_tokenize(chunk))
    if not chunk_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in chunk_terms)
    return hits / len(query_terms)


def _collect_source_files(sandbox, root: str) -> list[dict[str, Any]]:
    """Walk sources/ up to two levels deep, returning text file entries."""
    collected: list[dict[str, Any]] = []
    try:
        top_entries = sandbox.list_directory(root)
    except Exception:
        return collected
    directories: list[str] = []
    for entry in top_entries:
        path = str(entry.get("path") or "")
        if entry.get("is_dir"):
            directories.append(path)
        else:
            collected.append(entry)
    for directory in directories:
        try:
            for entry in sandbox.list_directory(directory):
                if not entry.get("is_dir"):
                    collected.append(entry)
        except Exception:
            continue
    return [
        entry
        for entry in collected
        if str(entry.get("name") or "").lower().endswith(_TEXT_EXTENSIONS)
        and int(entry.get("size") or 0) <= _MAX_FILE_BYTES
    ][:_MAX_FILES]


@normalized_tool(needs_sandbox=True)
async def search_sources(query: str, max_results: int = 0) -> dict[str, Any]:
    """Search the workspace ``sources/`` folder for chunks relevant to a query.

    Use this instead of re-reading whole source files when you need specific
    facts from material already collected (web search dumps, scraped pages,
    uploaded documents). Results include the source file path for citation.

    Args:
        query: What to look for, in plain words.
        max_results: Optional cap on returned chunks (default from settings).

    Returns:
        NormalizedToolResult with the top matching chunks and their sources.
    """
    from nexus.tools._context import get_sandbox
    from nexus.tools.workspace import get_active_workspace_path

    cleaned_query = " ".join(str(query or "").split())
    if not cleaned_query:
        return tool_error("query is required", error_code="INVALID_INPUT")
    query_terms = _tokenize(cleaned_query)
    if not query_terms:
        return tool_error("query has no searchable terms", error_code="INVALID_INPUT")

    limit = max_results if max_results and max_results > 0 else settings.retrieval_max_results

    try:
        workspace_path = get_active_workspace_path()
    except Exception as exc:
        return tool_error(
            f"No active workspace: {exc}",
            error_code="NO_WORKSPACE",
            suggested_alternatives=["prepare_task_workspace"],
        )

    sandbox = get_sandbox()
    sources_root = f"{workspace_path.rstrip('/')}/sources"
    files = _collect_source_files(sandbox, sources_root)
    if not files:
        return tool_error(
            "No readable source files found under sources/. Collect material "
            "first (web_search and scrape_web_page save into sources/).",
            error_code="NOT_FOUND",
            suggested_alternatives=["web_search", "list_workspace_files"],
        )

    scored: list[tuple[float, str, str]] = []
    for entry in files:
        path = str(entry.get("path") or "")
        try:
            content = sandbox.read_text_file(path)
        except Exception:
            continue
        relative = path[len(workspace_path) :].lstrip("/") if path.startswith(workspace_path) else path
        for chunk in _chunk_text(content):
            score = _score_chunk(query_terms, chunk)
            if score > 0:
                scored.append((score, relative, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:limit]
    if not top:
        return tool_error(
            f"No source chunks matched '{cleaned_query}'.",
            error_code="NOT_FOUND",
            suggested_alternatives=["web_search", "read_workspace_file"],
        )

    return tool_success(
        f"Found {len(top)} relevant chunk(s) across sources/ for '{cleaned_query}'.",
        results=[
            {"source": source, "score": round(score, 3), "text": chunk}
            for score, source, chunk in top
        ],
        files_scanned=len(files),
    )
