# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Agent skills management endpoints."""

from __future__ import annotations

import ipaddress
import io
import socket
import zipfile
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.dependencies import get_history_repository
from nexus.models import AgentSkillImportRequest, AgentSkillUpsertRequest, StatusMessage
from nexus.skill_catalog import CatalogFetchError, CatalogSourceError, load_catalog
from nexus.skill_format import SkillFormatError, parse_skill_md, render_skill_md, normalize_skill_files
from nexus.skill_import import (
    companion_urls_for_skill,
    decode_zip_b64,
    files_from_github_contents,
    github_contents_api_url,
    github_skill_subdirs,
    unpack_skill_zip,
)
from nexus.skills import (
    build_agent_skills_update,
    get_agent_skill,
    list_agent_skills,
    public_skill,
    skill_from_parsed,
    _custom_skill,
    _now_iso,
)

router = APIRouter()
history_repository = get_history_repository()

_MAX_REMOTE_SKILL_BYTES = 200_000


def _public(skill: dict) -> dict:
    return public_skill(skill)


@router.get("/api/v1/skills")
async def list_skills(user: AuthenticatedUser = Depends(require_current_user)):
    user_settings = await history_repository.get_user_settings(user.uid)
    skills = [_public(skill) for skill in list_agent_skills(user_settings, include_files=True)]
    return {"skills": skills}


@router.get("/api/v1/skills/catalog")
async def list_skill_catalog(
    source: str | None = None,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    installed_ids = {str(skill.get("skill_id") or "") for skill in list_agent_skills(user_settings)}
    try:
        catalog = await load_catalog(
            source,
            fetch_json=_catalog_fetch_json,
            fetch_text=_fetch_remote_text,
            installed_ids=installed_ids,
        )
    except CatalogSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CatalogFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return catalog


@router.post("/api/v1/skills")
async def create_skill(
    payload: AgentSkillUpsertRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not payload.name or not payload.instructions:
        raise HTTPException(status_code=400, detail="Skill name and instructions are required.")
    user_settings = await history_repository.get_user_settings(user.uid)
    state = build_agent_skills_update(user_settings)["agentSkills"]
    custom = list(state.get("custom") or [])

    skill = _custom_skill(
        {
            "name": payload.name,
            "category": payload.category or "Custom",
            "description": payload.description or "",
            "trigger": payload.trigger or "",
            "instructions": payload.instructions,
            "enabled": payload.enabled if payload.enabled is not None else True,
        }
    )
    if not skill:
        raise HTTPException(status_code=400, detail="Invalid skill payload.")
    custom.append(skill)
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=custom),
    )
    return {"skill": _public(skill)}


@router.post("/api/v1/skills/import")
async def import_skill(
    payload: AgentSkillImportRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    files = dict(payload.files or {})
    skill_md = (payload.skill_md or "").strip()
    if payload.zip_b64:
        try:
            zip_md, zip_files = unpack_skill_zip(decode_zip_b64(payload.zip_b64))
        except SkillFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        skill_md = skill_md or zip_md
        files = {**zip_files, **files}
    if payload.source_url and not skill_md:
        skill_md = await _fetch_remote_skill_md(payload.source_url)
    if payload.source_url and skill_md:
        try:
            companions = await _fetch_skill_companion_files(payload.source_url, skill_md)
            files = {**companions, **files}
        except Exception:
            pass
    if not skill_md:
        raise HTTPException(status_code=400, detail="Provide skill_md, source_url, or zip_b64.")
    try:
        parsed = parse_skill_md(skill_md)
    except SkillFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_settings = await history_repository.get_user_settings(user.uid)
    state = build_agent_skills_update(user_settings)["agentSkills"]
    custom = list(state.get("custom") or [])
    existing = next((item for item in custom if item.get("skill_id") == parsed.name), None)
    skill = skill_from_parsed(
        parsed,
        files=files,
        enabled=payload.enabled,
        existing=existing,
    )
    if not skill:
        raise HTTPException(status_code=400, detail="Imported SKILL.md did not produce a valid skill.")

    updated_custom = [item for item in custom if item.get("skill_id") != skill["skill_id"]]
    updated_custom.append(skill)
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=updated_custom),
    )
    return {"skill": _public(skill)}


@router.get("/api/v1/skills/{skill_id}/export")
async def export_skill(
    skill_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    skill = get_agent_skill(user_settings, skill_id, include_files=True)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_md = render_skill_md(skill)
    files = normalize_skill_files(skill.get("files"))
    filename_base = str(skill.get("skill_id") or "skill")
    if not files:
        encoded = skill_md.encode("utf-8")
        return StreamingResponse(
            io.BytesIO(encoded),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}-SKILL.md"'},
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SKILL.md", skill_md)
        for rel, content in files.items():
            archive.writestr(rel, content)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.zip"'},
    )


@router.get("/api/v1/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    skill = get_agent_skill(user_settings, skill_id, include_files=True)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"skill": skill}


@router.patch("/api/v1/skills/{skill_id}")
async def update_skill(
    skill_id: str,
    payload: AgentSkillUpsertRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    skills = list_agent_skills(user_settings)
    existing = next((skill for skill in skills if skill["skill_id"] == skill_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Skill not found")

    state = build_agent_skills_update(user_settings)["agentSkills"]
    disabled_defaults = set(state.get("disabledDefaults") or [])
    custom = list(state.get("custom") or [])

    if existing.get("source") != "user" and not any(item.get("skill_id") == skill_id for item in custom):
        if payload.enabled is True:
            disabled_defaults.discard(skill_id)
        elif payload.enabled is False:
            disabled_defaults.add(skill_id)
        await history_repository.update_user_settings(
            user.uid,
            build_agent_skills_update(user_settings, disabled_defaults=disabled_defaults),
        )
        updated = next(skill for skill in list_agent_skills(await history_repository.get_user_settings(user.uid)) if skill["skill_id"] == skill_id)
        return {"skill": _public(updated)}

    updated_custom = []
    updated = None

    for skill in custom:
        if skill.get("skill_id") != skill_id:
            updated_custom.append(skill)
            continue
        candidate = {
            **skill,
            "name": payload.name if payload.name is not None else skill.get("name"),
            "category": payload.category if payload.category is not None else skill.get("category"),
            "description": payload.description if payload.description is not None else skill.get("description"),
            "trigger": payload.trigger if payload.trigger is not None else skill.get("trigger"),
            "instructions": payload.instructions if payload.instructions is not None else skill.get("instructions"),
            "enabled": payload.enabled if payload.enabled is not None else skill.get("enabled", True),
            "updated_at": _now_iso(),
        }
        updated = _custom_skill(candidate)
        if updated:
            updated_custom.append(updated)
    if not updated:
        raise HTTPException(status_code=400, detail="Invalid skill update.")
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=updated_custom),
    )
    return {"skill": _public(updated)}


@router.delete("/api/v1/skills/{skill_id}", response_model=StatusMessage)
async def delete_skill(
    skill_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    user_settings = await history_repository.get_user_settings(user.uid)
    state = build_agent_skills_update(user_settings)["agentSkills"]
    custom = [skill for skill in (state.get("custom") or []) if skill.get("skill_id") != skill_id]
    if len(custom) == len(state.get("custom") or []):
        raise HTTPException(status_code=404, detail="Only user-created skills can be deleted.")
    await history_repository.update_user_settings(
        user.uid,
        build_agent_skills_update(user_settings, custom=custom),
    )
    return StatusMessage(status="deleted")


def _normalize_skill_source_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if host in {"github.com", "www.github.com"} and len(parts) >= 4:
        owner, repo, kind, ref, *rest = parts
        if kind == "blob" and rest:
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{'/'.join(rest)}"
        if kind == "tree":
            suffix = "/".join(rest) if rest else ""
            if suffix and not suffix.endswith("SKILL.md"):
                suffix = f"{suffix.rstrip('/')}/SKILL.md"
            elif not suffix:
                suffix = "SKILL.md"
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{suffix}"
    return url.strip()


def _is_public_https_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or not ip.is_global:
            return False
    return True


async def _fetch_remote_skill_md(url: str) -> str:
    normalized = _normalize_skill_source_url(url)
    if not _is_public_https_url(normalized):
        raise HTTPException(status_code=400, detail="source_url must be a public https URL.")
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(normalized)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail="Could not fetch SKILL.md from source_url.") from exc
    content = response.content or b""
    if len(content) > _MAX_REMOTE_SKILL_BYTES:
        raise HTTPException(status_code=400, detail="Remote SKILL.md is too large.")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Remote SKILL.md is not valid UTF-8.") from exc


async def _fetch_remote_text(url: str) -> str | None:
    if not _is_public_https_url(url):
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "CoComputer", "Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return None
    content = response.content or b""
    if len(content) > _MAX_REMOTE_SKILL_BYTES:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


async def _catalog_fetch_json(url: str) -> Any:
    payload = await _fetch_github_json(url)
    if payload is None:
        raise CatalogFetchError("Could not read GitHub skill tree.")
    return payload


async def _fetch_github_json(url: str) -> Any:
    if not _is_public_https_url(url):
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "CoComputer", "Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return None


async def _fetch_skill_companion_files(source_url: str, skill_md: str) -> dict[str, str]:
    files: dict[str, str] = {}
    normalized = _normalize_skill_source_url(source_url)
    candidates: list[tuple[str, str]] = []
    api_url = github_contents_api_url(source_url) or github_contents_api_url(normalized)
    listing = await _fetch_github_json(api_url) if api_url else None
    if listing is not None:
        candidates.extend(files_from_github_contents(listing))
        for dirname, dir_url in github_skill_subdirs(listing):
            sub = await _fetch_github_json(dir_url)
            if sub is None:
                continue
            candidates.extend(files_from_github_contents(sub, prefix=dirname))
    if not candidates:
        candidates = companion_urls_for_skill(normalized, skill_md)
    for rel, url in candidates:
        if rel in files:
            continue
        content = await _fetch_remote_text(url)
        if content:
            files[rel] = content
    return files
