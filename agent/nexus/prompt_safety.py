# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Escaping for text that enters the model prompt from outside the runtime.

Runtime instructions travel only inside ``<runtime kind="...">`` blocks (see
:mod:`nexus.prompt_assembly`). Anything typed by the user, read from a file
name, an MCP description, or memory must not be able to fake one. This is
prompt hardening, not an authorization boundary: tool policy and approvals
still gate every action.
"""

from __future__ import annotations

import re

# Internal markers the runtime itself emits. In untrusted text they are
# neutralized by swapping the ASCII bracket for a look-alike, so the model
# (and our own parsers, e.g. ``text.startswith("[SYSTEM")``) never treat
# them as runtime instructions.
_BRACKET_DIRECTIVE_RE = re.compile(
    r"\[(?=\s*(?:SYSTEM|CONTINUE TASK|END CONTINUE TASK|UNATTENDED|RUNTIME|"
    r"USER MEMORY|END USER MEMORY|UPLOADED FILES|USER-SELECTED TOOLS|DIRECTIVE)\b)",
    re.IGNORECASE,
)
_TAG_DIRECTIVE_RE = re.compile(r"<(?=\s*/?\s*(?:runtime|untrusted)\b)", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_LABEL_RE = re.compile(r"[^A-Za-z0-9_.:\-]")


def escape_internal_delimiters(text: str) -> str:
    """Neutralize runtime markers inside untrusted text (model view only)."""
    raw = str(text or "")
    raw = _TAG_DIRECTIVE_RE.sub("&lt;", raw)
    return _BRACKET_DIRECTIVE_RE.sub("\uff3b", raw)


def clean_inline(text: str, cap: int = 200) -> str:
    """One-line, bracket-free, bounded rendering of an untrusted name."""
    raw = _CONTROL_RE.sub(" ", str(text or ""))
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = raw.replace("[", "(").replace("]", ")").replace("<", "\u2039").replace(">", "\u203a")
    if len(raw) > cap:
        raw = raw[: max(0, cap - 1)].rstrip() + "\u2026"
    return raw


def fence_untrusted(label: str, text: str) -> str:
    """Wrap external content so the model reads it as data, not instructions."""
    source = _LABEL_RE.sub("_", str(label or "external"))[:64] or "external"
    body = escape_internal_delimiters(str(text or "").strip())
    return f'<untrusted source="{source}">\n{body}\n</untrusted>'


__all__ = ["clean_inline", "escape_internal_delimiters", "fence_untrusted"]
