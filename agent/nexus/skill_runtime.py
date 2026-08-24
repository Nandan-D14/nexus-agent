# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Mount enabled Agent Skills into the sandbox filesystem."""

from __future__ import annotations

import logging
from typing import Any

from nexus.skill_format import render_skill_md, safe_skill_relpath, skill_sandbox_path
from nexus.skills import list_agent_skills

logger = logging.getLogger("nexus.skills")


def sync_skills_to_sandbox(sandbox: Any, user_settings: dict[str, Any] | None) -> int:
    """Write SKILL.md + resource files for every enabled skill. Returns files written."""
    if sandbox is None or not getattr(sandbox, "is_alive", False):
        return 0
    written = 0
    for skill in list_agent_skills(user_settings, include_files=True):
        if not skill.get("enabled"):
            continue
        skill_id = str(skill.get("skill_id") or "").strip()
        if not skill_id:
            continue
        root = skill_sandbox_path(skill_id)
        try:
            sandbox.ensure_directory(root)
            sandbox.write_text_file(f"{root}/SKILL.md", render_skill_md(skill))
            written += 1
            for rel, content in (skill.get("files") or {}).items():
                safe = safe_skill_relpath(str(rel))
                if not safe or safe == "SKILL.md":
                    continue
                sandbox.write_text_file(f"{root}/{safe}", str(content))
                written += 1
        except Exception:
            logger.warning("Failed to mount skill %s into sandbox", skill_id, exc_info=True)
    return written


sync_skills_to_sandbox = sync_skills_to_sandbox
