# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Browse public GitHub Agent Skills libraries (SKILL.md catalogs)."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Awaitable, Callable, Sequence
from urllib.parse import urlparse

from nexus.skill_format import SkillFormatError, parse_skill_md

FetchJson = Callable[[str], Awaitable[Any]]
FetchText = Callable[[str], Awaitable[str | None]]

_MAX_SKILLS_PER_SOURCE = 40
_MAX_TREE_ENTRIES = 8_000
_CACHE_TTL_SECONDS = 3600.0
_FETCH_CONCURRENCY = 8
_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_GITHUB_HOSTS = {"github.com", "www.github.com"}
_SOURCE_AVAILABLE_IDS = frozenset({"docx", "pdf", "pptx", "xlsx"})
_SKILL_CONTAINERS = ("", "skills", "skills/.curated", "skills/.experimental", "skills/.system")

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


@dataclass(frozen=True)
class CatalogSource:
    owner: str
    repo: str
    ref: str
    prefix: str
    source_id: str
    label: str

    @property
    def repo_slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def cache_key(self) -> str:
        prefix = self.prefix.strip("/")
        return f"{self.owner}/{self.repo}@{self.ref}:{prefix}"


DEFAULT_SOURCES: tuple[CatalogSource, ...] = (
    CatalogSource("anthropics", "skills", "main", "skills", "anthropics", "Anthropic"),
    CatalogSource("vercel-labs", "agent-skills", "main", "", "vercel", "Vercel"),
)

_DEFAULT_BY_ID = {item.source_id: item for item in DEFAULT_SOURCES}


class CatalogSourceError(ValueError):
    """Raised when a catalog source URL is not a public GitHub repo."""


class CatalogFetchError(RuntimeError):
    """Raised when GitHub cannot be read for a catalog source."""


def clear_catalog_cache() -> None:
    _cache.clear()


def default_source_summaries() -> list[dict[str, str]]:
    return [
        {
            "id": item.source_id,
            "label": item.label,
            "repo": item.repo_slug,
        }
        for item in DEFAULT_SOURCES
    ]


def parse_github_source(value: str | None) -> CatalogSource | None:
    """Parse a catalog source id, owner/repo, or public GitHub URL.

    Returns None when value is empty (caller should use default sources).
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in _DEFAULT_BY_ID:
        return _DEFAULT_BY_ID[lowered]
    if lowered in {"anthropics/skills", "github.com/anthropics/skills"}:
        return _DEFAULT_BY_ID["anthropics"]
    if lowered in {"vercel-labs/agent-skills", "github.com/vercel-labs/agent-skills"}:
        return _DEFAULT_BY_ID["vercel"]

    if "://" in raw or lowered.startswith("github.com/") or lowered.startswith("www.github.com/"):
        return _parse_github_url(raw)
    parts = [item for item in raw.strip("/").split("/") if item]
    if len(parts) < 2:
        raise CatalogSourceError("Source must be owner/repo or a GitHub URL.")
    return _source_from_parts(parts[0], parts[1], "main", "/".join(parts[2:]), source_id="github")


def _parse_github_url(url: str) -> CatalogSource:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme != "https":
        raise CatalogSourceError("Only public https GitHub URLs are allowed.")
    host = (parsed.hostname or "").lower()
    if host not in _GITHUB_HOSTS:
        raise CatalogSourceError("Catalog source must be a public github.com repository.")
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise CatalogSourceError("Catalog source must be a public github.com repository.")
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if len(parts) < 2:
        raise CatalogSourceError("Source must be owner/repo or a GitHub URL.")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = "main"
    prefix_parts: list[str] = []
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        ref = parts[3]
        rest = parts[4:]
        if rest and rest[-1].lower() == "skill.md":
            rest = rest[:-1]
        prefix_parts = rest
    elif len(parts) > 2:
        prefix_parts = parts[2:]
    return _source_from_parts(owner, repo, ref, "/".join(prefix_parts), source_id="github")


def _source_from_parts(owner: str, repo: str, ref: str, prefix: str, *, source_id: str) -> CatalogSource:
    owner = owner.strip()
    repo = repo.strip()
    ref = (ref or "main").strip() or "main"
    if not _GITHUB_NAME_RE.fullmatch(owner) or not _GITHUB_NAME_RE.fullmatch(repo):
        raise CatalogSourceError("Invalid GitHub owner or repository name.")
    if ".." in owner or ".." in repo or ".." in ref:
        raise CatalogSourceError("Invalid GitHub owner or repository name.")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref):
        raise CatalogSourceError("Invalid GitHub ref.")
    safe_prefix = "/".join(
        part for part in prefix.replace("\\", "/").split("/") if part and part not in {".", ".."}
    )
    known = next(
        (
            item
            for item in DEFAULT_SOURCES
            if item.owner.lower() == owner.lower() and item.repo.lower() == repo.lower()
        ),
        None,
    )
    if known and (not safe_prefix or safe_prefix == known.prefix):
        if ref == known.ref:
            return known
        return CatalogSource(known.owner, known.repo, ref, known.prefix, known.source_id, known.label)
    return CatalogSource(owner, repo, ref, safe_prefix, source_id, f"{owner}/{repo}")


def github_tree_api_url(source: CatalogSource) -> str:
    return f"https://api.github.com/repos/{source.owner}/{source.repo}/git/trees/{source.ref}?recursive=1"


def raw_skill_md_url(source: CatalogSource, path: str) -> str:
    return f"https://raw.githubusercontent.com/{source.owner}/{source.repo}/{source.ref}/{path.lstrip('/')}"


def github_blob_url(source: CatalogSource, path: str) -> str:
    return f"https://github.com/{source.owner}/{source.repo}/blob/{source.ref}/{path.lstrip('/')}"


def github_tree_url(source: CatalogSource, path: str) -> str:
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    suffix = f"/{folder}" if folder else ""
    return f"https://github.com/{source.owner}/{source.repo}/tree/{source.ref}{suffix}"


def tree_paths_from_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    tree = payload.get("tree")
    if not isinstance(tree, list):
        return []
    paths: list[str] = []
    for item in tree[:_MAX_TREE_ENTRIES]:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "").replace("\\", "/").strip("/")
        if path:
            paths.append(path)
    return paths


def discover_skill_md_paths(paths: Sequence[str], *, prefix: str = "") -> list[str]:
    """Find SKILL.md files using the skills CLI layout (root + skills/, max 3 levels)."""
    skill_files = [
        path.replace("\\", "/").strip("/")
        for path in paths
        if path and (path.replace("\\", "/").strip("/").lower() == "skill.md" or path.replace("\\", "/").lower().endswith("/skill.md"))
    ]
    containers = [prefix.strip("/")] if prefix.strip("/") else list(_SKILL_CONTAINERS)
    found: list[str] = []
    seen: set[str] = set()
    for container in containers:
        for path in skill_files:
            rel = _relative_to_container(path, container)
            if rel is None:
                continue
            parts = PurePosixPath(rel).parts
            if any(
                part.startswith(".") and part not in {".curated", ".experimental", ".system"}
                for part in parts[:-1]
            ):
                continue
            depth = len(parts) - 1
            if depth > 3:
                continue
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(path)
    found.sort(key=lambda item: (item.count("/"), item.lower()))
    return _apply_shadowing(found)[:_MAX_SKILLS_PER_SOURCE]


def _relative_to_container(path: str, container: str) -> str | None:
    if not container:
        return path
    prefix = container.strip("/")
    lower = path.lower()
    prefix_lower = prefix.lower()
    if lower == f"{prefix_lower}/skill.md":
        return path.split("/", 1)[-1]
    if not lower.startswith(prefix_lower + "/"):
        return None
    return path[len(prefix) + 1 :]


def _apply_shadowing(paths: Sequence[str]) -> list[str]:
    kept: list[str] = []
    folders: list[str] = []
    for path in paths:
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        if any(folder == parent or folder.startswith(parent + "/") for parent in folders if parent):
            continue
        kept.append(path)
        if folder:
            folders.append(folder)
    return kept


def is_source_available(owner: str, skill_id: str) -> bool:
    return owner.lower() == "anthropics" and skill_id in _SOURCE_AVAILABLE_IDS


def catalog_item_from_parsed(
    parsed: Any,
    *,
    source: CatalogSource,
    path: str,
) -> dict[str, Any]:
    skill_id = str(parsed.name)
    restricted = is_source_available(source.owner, skill_id)
    license_value = str(parsed.license or "").strip()
    if restricted and not license_value:
        license_value = "Source-available"
    display = skill_id.replace("-", " ").title()
    return {
        "id": skill_id,
        "name": display,
        "description": parsed.description,
        "license": license_value,
        "source": source.source_id,
        "source_label": source.label,
        "source_url": github_blob_url(source, path),
        "html_url": github_tree_url(source, path),
        "restricted": restricted,
        "category": parsed.category,
    }


async def load_source_catalog(
    source: CatalogSource,
    *,
    fetch_json: FetchJson,
    fetch_text: FetchText,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    now = time.monotonic()
    if use_cache:
        cached = _cache.get(source.cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return [dict(item) for item in cached[1]]

    payload = await fetch_json(github_tree_api_url(source))
    if not isinstance(payload, dict) or not isinstance(payload.get("tree"), list):
        raise CatalogFetchError(f"Could not read the GitHub tree for {source.repo_slug}.")
    paths = discover_skill_md_paths(tree_paths_from_payload(payload), prefix=source.prefix)
    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def load_one(path: str) -> dict[str, Any] | None:
        async with semaphore:
            text = await fetch_text(raw_skill_md_url(source, path))
        if not text:
            return None
        try:
            parsed = parse_skill_md(text)
        except SkillFormatError:
            return None
        return catalog_item_from_parsed(parsed, source=source, path=path)

    items = [item for item in await asyncio.gather(*(load_one(path) for path in paths)) if item]
    items.sort(key=lambda item: str(item.get("name") or "").lower())
    _cache[source.cache_key] = (now, [dict(item) for item in items])
    return items


async def load_catalog(
    source_value: str | None,
    *,
    fetch_json: FetchJson,
    fetch_text: FetchText,
    installed_ids: set[str] | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    parsed_source = parse_github_source(source_value)
    sources = [parsed_source] if parsed_source else list(DEFAULT_SOURCES)
    skills: list[dict[str, Any]] = []
    errors: list[str] = []
    installed = installed_ids or set()
    for source in sources:
        try:
            items = await load_source_catalog(
                source,
                fetch_json=fetch_json,
                fetch_text=fetch_text,
                use_cache=use_cache,
            )
        except Exception as exc:
            errors.append(f"{source.label}: {exc}")
            continue
        for item in items:
            item["installed"] = item["id"] in installed
            skills.append(item)
    return {
        "sources": default_source_summaries(),
        "skills": skills,
        "error": "; ".join(errors) if errors else None,
    }
