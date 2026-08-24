# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Import helpers for Agent Skills packages (SKILL.md, zip, GitHub folders)."""

from __future__ import annotations

import base64
import io
import re
import zipfile
from typing import Any
from urllib.parse import urljoin, urlparse

from nexus.skill_format import SKILL_MD_FILENAME, SkillFormatError, safe_skill_relpath

_MAX_ZIP_BYTES = 2_000_000
_MAX_TEXT_FILE_BYTES = 80_000
_MAX_PACKAGE_FILES = 20
_TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".csv",
    ".sh",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".xml",
    ".prompt",
}
_REL_PATH_RE = re.compile(
    r"(?:`|\(|\[)((?:scripts|references|assets|files)/[A-Za-z0-9._/\-]+\.[A-Za-z0-9]+)"
)
_SKILL_MD_NAMES = {"skill.md"}


def decode_zip_b64(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw:
        raise SkillFormatError("zip_b64 is empty.")
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception as exc:
        raise SkillFormatError("zip_b64 is not valid base64.") from exc
    if len(data) > _MAX_ZIP_BYTES:
        raise SkillFormatError("Skill zip is too large.")
    return data


def unpack_skill_zip(data: bytes) -> tuple[str, dict[str, str]]:
    if len(data) > _MAX_ZIP_BYTES:
        raise SkillFormatError("Skill zip is too large.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillFormatError("Uploaded file is not a valid zip.") from exc

    members = [
        name
        for name in archive.namelist()
        if name and not name.endswith("/") and "__macosx/" not in name.lower()
    ]
    prefix = _common_prefix(members)
    skill_md = ""
    files: dict[str, str] = {}
    for name in members:
        rel = name[len(prefix) :] if prefix and name.startswith(prefix) else name
        rel = rel.replace("\\", "/").lstrip("/")
        lower = rel.lower()
        if lower.rsplit("/", 1)[-1] in _SKILL_MD_NAMES and "/" not in rel.strip("/"):
            skill_md = _read_zip_text(archive, name)
            continue
        safe = safe_skill_relpath(rel)
        if not safe or safe == SKILL_MD_FILENAME:
            continue
        if not any(safe.lower().endswith(suffix) for suffix in _TEXT_SUFFIXES):
            continue
        if len(files) >= _MAX_PACKAGE_FILES:
            break
        content = _read_zip_text(archive, name)
        if content:
            files[safe] = content
    if not skill_md.strip():
        raise SkillFormatError("Zip must contain a SKILL.md file at the skill root.")
    return skill_md, files


def referenced_skill_paths(skill_md: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _REL_PATH_RE.finditer(skill_md or ""):
        rel = safe_skill_relpath(match.group(1))
        if not rel or rel in seen or rel == SKILL_MD_FILENAME:
            continue
        seen.add(rel)
        found.append(rel)
    return found


def companion_urls_for_skill(source_url: str, skill_md: str) -> list[tuple[str, str]]:
    """Return (relative_path, absolute_url) pairs next to a remote SKILL.md."""
    parsed = urlparse(source_url)
    if parsed.scheme != "https":
        return []
    base = source_url
    if base.lower().endswith("skill.md"):
        base = base[: base.rfind("/") + 1]
    elif not base.endswith("/"):
        base += "/"
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rel in referenced_skill_paths(skill_md):
        if rel in seen:
            continue
        seen.add(rel)
        pairs.append((rel, urljoin(base, rel)))
    return pairs


def github_contents_api_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").lower()
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if host in {"github.com", "www.github.com"} and len(parts) >= 4:
        owner, repo, kind, ref, *rest = parts
        if kind not in {"blob", "tree"}:
            return None
        directory = rest[:-1] if rest and rest[-1].lower() == "skill.md" else rest
        dir_path = "/".join(directory)
        suffix = f"/{dir_path}" if dir_path else ""
        return f"https://api.github.com/repos/{owner}/{repo}/contents{suffix}?ref={ref}"
    if host == "raw.githubusercontent.com" and len(parts) >= 3:
        owner, repo, ref, *rest = parts
        directory = rest[:-1] if rest and rest[-1].lower() == "skill.md" else rest
        dir_path = "/".join(directory)
        suffix = f"/{dir_path}" if dir_path else ""
        return f"https://api.github.com/repos/{owner}/{repo}/contents{suffix}?ref={ref}"
    return None


def files_from_github_contents(payload: Any, *, prefix: str = "") -> list[tuple[str, str]]:
    if not isinstance(payload, list):
        payload = [payload] if isinstance(payload, dict) else []
    files: list[tuple[str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        name = str(item.get("name") or "")
        if name.lower() in _SKILL_MD_NAMES:
            continue
        rel_name = f"{prefix.rstrip('/')}/{name}" if prefix else name
        rel = safe_skill_relpath(rel_name)
        download = str(item.get("download_url") or "").strip()
        if not rel or not download or rel == SKILL_MD_FILENAME:
            continue
        if not any(rel.lower().endswith(suffix) for suffix in _TEXT_SUFFIXES):
            continue
        files.append((rel, download))
    return files[:_MAX_PACKAGE_FILES]


def github_skill_subdirs(payload: Any) -> list[tuple[str, str]]:
    if not isinstance(payload, list):
        payload = [payload] if isinstance(payload, dict) else []
    dirs: list[tuple[str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "dir":
            continue
        name = str(item.get("name") or "")
        api_url = str(item.get("url") or "").strip()
        if name in {"scripts", "references", "assets", "files"} and api_url:
            dirs.append((name, api_url))
    return dirs


def _common_prefix(names: list[str]) -> str:
    normalized = [name.replace("\\", "/") for name in names]
    tops = {name.split("/", 1)[0] for name in normalized if name}
    if len(tops) != 1:
        return ""
    top = next(iter(tops))
    if any("/" not in name for name in normalized):
        return ""
    return f"{top}/"


def _read_zip_text(archive: zipfile.ZipFile, name: str) -> str:
    info = archive.getinfo(name)
    if info.file_size > _MAX_TEXT_FILE_BYTES:
        return ""
    try:
        raw = archive.read(name)
    except Exception:
        return ""
    if len(raw) > _MAX_TEXT_FILE_BYTES:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def is_probably_skill_zip(filename: str) -> bool:
    return str(filename or "").lower().endswith(".zip")
