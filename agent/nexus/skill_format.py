# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Agent Skills SKILL.md parse/serialize (https://agentskills.io/specification)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_MD_FILENAME = "SKILL.md"
SKILL_SANDBOX_ROOT = "/home/user/skills"

_MAX_NAME = 64
_MAX_DESCRIPTION = 1024
_MAX_COMPAT = 500
_MAX_BODY = 16_000
_MAX_FILE_BYTES = 80_000
_MAX_FILES = 20
_MAX_FILES_TOTAL = 200_000


class SkillFormatError(ValueError):
    """Raised when SKILL.md is missing or invalid."""


@dataclass
class ParsedSkill:
    name: str
    description: str
    body: str
    license: str = ""
    compatibility: str = ""
    allowed_tools: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def trigger(self) -> str:
        return (self.metadata.get("cocomputer.trigger") or self.description).strip()

    @property
    def category(self) -> str:
        return (self.metadata.get("cocomputer.category") or "Custom").strip() or "Custom"


def is_valid_skill_name(value: str) -> bool:
    name = str(value or "").strip()
    return bool(name) and len(name) <= _MAX_NAME and bool(SKILL_NAME_RE.fullmatch(name))


def slugify_skill_name(value: str, fallback: str = "skill") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return (cleaned[:_MAX_NAME] or fallback).strip("-") or fallback


def skill_sandbox_path(skill_id: str) -> str:
    safe = slugify_skill_name(skill_id)
    return f"{SKILL_SANDBOX_ROOT}/{safe}"


def safe_skill_relpath(path: str) -> str | None:
    raw = str(path or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or raw.startswith("~"):
        return None
    posix = PurePosixPath(raw)
    if posix.is_absolute() or not posix.parts:
        return None
    if any(part in {".", ".."} for part in posix.parts):
        return None
    rel = str(posix)
    if rel == SKILL_MD_FILENAME:
        return SKILL_MD_FILENAME
    return rel


def normalize_skill_files(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    files: dict[str, str] = {}
    total = 0
    for key, value in raw.items():
        rel = safe_skill_relpath(str(key))
        if not rel or rel == SKILL_MD_FILENAME:
            continue
        content = str(value or "")
        if len(content.encode("utf-8")) > _MAX_FILE_BYTES:
            continue
        total += len(content.encode("utf-8"))
        if total > _MAX_FILES_TOTAL or len(files) >= _MAX_FILES:
            break
        files[rel] = content
    return files


def parse_skill_md(text: str) -> ParsedSkill:
    source = str(text or "").lstrip("\ufeff")
    if not source.startswith("---"):
        raise SkillFormatError("SKILL.md must start with YAML frontmatter delimited by ---.")
    rest = source[3:]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    closer = re.search(r"\n---[ \t]*\r?\n", rest)
    if closer is None:
        end_only = re.search(r"\n---[ \t]*\s*$", rest)
        if end_only is None:
            raise SkillFormatError("SKILL.md frontmatter is not closed with ---.")
        yaml_text = rest[: end_only.start()]
        body = ""
    else:
        yaml_text = rest[: closer.start()]
        body = rest[closer.end() :]
    fields = _parse_simple_yaml(yaml_text)
    name = slugify_skill_name(str(fields.get("name") or ""))
    description = str(fields.get("description") or "").strip()
    if not name or not is_valid_skill_name(name):
        raise SkillFormatError("SKILL.md requires a valid name (lowercase letters, numbers, hyphens).")
    if not description:
        raise SkillFormatError("SKILL.md requires a non-empty description.")
    metadata_raw = fields.get("metadata")
    metadata = {
        str(key): str(val)
        for key, val in (metadata_raw.items() if isinstance(metadata_raw, dict) else [])
        if str(key).strip()
    }
    return ParsedSkill(
        name=name[:_MAX_NAME],
        description=description[:_MAX_DESCRIPTION],
        body=body.strip()[:_MAX_BODY],
        license=str(fields.get("license") or "")[:200],
        compatibility=str(fields.get("compatibility") or "")[:_MAX_COMPAT],
        allowed_tools=str(fields.get("allowed-tools") or fields.get("allowed_tools") or "")[:500],
        metadata=metadata,
    )


def render_skill_md(skill: dict[str, Any]) -> str:
    name = skill.get("skill_id") or slugify_skill_name(str(skill.get("name") or "skill"))
    if not is_valid_skill_name(str(name)):
        name = slugify_skill_name(str(skill.get("name") or name))
    description = str(skill.get("description") or skill.get("trigger") or skill.get("name") or "").strip()
    if not description:
        description = f"Use the {skill.get('name') or name} skill."
    metadata = dict(skill.get("metadata") or {})
    if skill.get("trigger"):
        metadata.setdefault("cocomputer.trigger", str(skill["trigger"]))
    if skill.get("category"):
        metadata.setdefault("cocomputer.category", str(skill["category"]))
    scope = skill.get("agent_scope") or skill.get("agent_scope")
    if scope:
        metadata.setdefault(
            "cocomputer.agent_scope",
            ", ".join(str(item) for item in scope),
        )
    lines = ["---", f"name: {name}", _yaml_scalar("description", description[:_MAX_DESCRIPTION])]
    license_value = str(skill.get("license") or "").strip()
    if license_value:
        lines.append(f"license: {license_value}")
    compatibility = str(skill.get("compatibility") or "").strip()
    if compatibility:
        lines.append(_yaml_scalar("compatibility", compatibility[:_MAX_COMPAT]))
    allowed = str(skill.get("allowed_tools") or "").strip()
    if allowed:
        lines.append(f"allowed-tools: {allowed}")
    if metadata:
        lines.append("metadata:")
        for key, value in metadata.items():
            lines.append(f"  {key}: {_quote_if_needed(str(value))}")
    lines.append("---")
    body = str(skill.get("instructions") or "").strip()
    if body:
        lines.append("")
        lines.append(body)
    lines.append("")
    return "\n".join(lines)


def _quote_if_needed(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[:#{}[\],&*?|>!%@`]', value) or value[0] in "\"'|" or "\n" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _yaml_scalar(key: str, value: str) -> str:
    if "\n" in value:
        block = "\n".join(f"  {line}" if line else "  " for line in value.splitlines())
        return f"{key}: |\n{block}"
    return f"{key}: {_quote_if_needed(value)}"


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used in SKILL.md frontmatter."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith(" ") or line.startswith("\t"):
            raise SkillFormatError("SKILL.md frontmatter has an unexpected indented line.")
        if ":" not in line:
            raise SkillFormatError(f"Invalid SKILL.md frontmatter line: {line[:80]}")
        key, remainder = line.split(":", 1)
        key = key.strip()
        remainder = remainder.strip()
        if key == "metadata":
            metadata, index = _parse_nested_map(lines, index + 1)
            result["metadata"] = metadata
            continue
        if remainder in {"|", ">"}:
            block, index = _parse_block_scalar(lines, index + 1)
            result[key] = block
            continue
        result[key] = _unquote(remainder)
        index += 1
    return result


def _parse_nested_map(lines: list[str], start: int) -> tuple[dict[str, str], int]:
    nested: dict[str, str] = {}
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if not line.startswith("  "):
            break
        stripped = line.strip()
        if stripped.startswith("#") or ":" not in stripped:
            index += 1
            continue
        key, remainder = stripped.split(":", 1)
        nested[key.strip()] = _unquote(remainder.strip())
        index += 1
    return nested, index


def _parse_block_scalar(lines: list[str], start: int) -> tuple[str, int]:
    collected: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if line and not line.startswith(" ") and not line.startswith("\t"):
            break
        collected.append(re.sub(r"^  ", "", line) if line.startswith("  ") else line[1:] if line.startswith("\t") else line)
        index += 1
    return "\n".join(collected).strip(), index


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        inner = text[1:-1]
        return inner.replace('\\"', '"').replace("\\n", "\n")
    return text


# Compatibility aliases for older import names.
parse_skill_md = parse_skill_md
SkillFormatError = SkillFormatError
safe_skill_relpath = safe_skill_relpath
normalize_skill_files = normalize_skill_files
skill_sandbox_path = skill_sandbox_path
SKILL_MD_FILENAME = SKILL_MD_FILENAME
render_skill_md = render_skill_md
