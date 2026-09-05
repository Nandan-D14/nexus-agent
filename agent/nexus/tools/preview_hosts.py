# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Make Vite (and similar) dev servers accept E2B preview hostnames.

Vite 6+ rejects requests whose Host header is not in ``server.allowedHosts``.
CoComputer previews use ``https://<port>-<sandboxId>.e2b.app``, so an unpatched
Vite config renders a black/white "Blocked request" page in the Preview tab.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import logging
import re
import shlex
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

VITE_CONFIG_NAMES = frozenset(
    {
        "vite.config.ts",
        "vite.config.js",
        "vite.config.mts",
        "vite.config.mjs",
        "vite.config.cjs",
    }
)
_VITE_PORTS = frozenset({5173, 4173, 5174})
_ALLOWED_HOSTS_ASSIGN = re.compile(
    r"allowedHosts\s*:\s*(true|false|True|False|\[[^\]]*\]|'[^']*'|\"[^\"]*\")",
    re.DOTALL,
)
_LONG_RUNNING_SERVER_RE = re.compile(
    r"(?is)(?:^|[;&|\n]\s*)(?:(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:dev|start|preview)\b"
    r"|npx\s+vite\b"
    r"|(?:npx\s+)?next\s+dev\b"
    r"|\bvite(?:\s|$)"
    r"|python3?\s+-m\s+http\.server\b"
    r"|flask\s+run\b"
    r"|uvicorn\b"
    r"|php\s+-S\b)"
)


def command_starts_long_running_server(command: str) -> bool:
    """True when the shell command is a web/dev server that never exits."""
    text = (command or "").strip()
    if not text or text.endswith("&"):
        return False
    return bool(_LONG_RUNNING_SERVER_RE.search(text))


def is_vite_config_path(path: str) -> bool:
    name = PurePosixPath(str(path or "").replace("\\", "/")).name.lower()
    return name in VITE_CONFIG_NAMES


def vite_config_allows_preview_hosts(source: str) -> bool:
    compact = re.sub(r"\s+", "", source or "")
    if "allowedHosts:true" in compact or "allowedHosts:True" in compact:
        return True
    if "allowedHosts" in compact and ".e2b.app" in compact:
        return True
    return False


def vite_host_is_blocked(body: str) -> bool:
    lower = (body or "").lower()
    compact = re.sub(r"\s+", "", lower)
    if "blocked request" in lower:
        return True
    return "not allowed" in lower and "allowedhosts" in compact


def patch_vite_config_source(source: str) -> str | None:
    """Return a patched vite config, or None when no edit is needed/possible."""
    text = source or ""
    if vite_config_allows_preview_hosts(text):
        return None
    if _ALLOWED_HOSTS_ASSIGN.search(text):
        patched = _ALLOWED_HOSTS_ASSIGN.sub("allowedHosts: true", text, count=1)
        return patched if patched != text else None
    server_open = re.search(r"\bserver\s*:\s*\{", text)
    if server_open:
        i = server_open.end()
        return text[:i] + "\n    allowedHosts: true," + text[i:]
    define = re.search(r"defineConfig\s*\(\s*\{", text)
    if define:
        i = define.end()
        return text[:i] + "\n  server: { host: true, allowedHosts: true }," + text[i:]
    default = re.search(r"export\s+default\s+\{", text)
    if default:
        i = default.end()
        return text[:i] + "\n  server: { host: true, allowedHosts: true }," + text[i:]
    return None


def maybe_patch_dev_server_config(relative_path: str, content: str) -> str:
    """Patch vite.config.* contents in-memory before they are written."""
    if not is_vite_config_path(relative_path):
        return content
    patched = patch_vite_config_source(content)
    return patched if patched is not None else content


def preview_hostname(url: str) -> str:
    try:
        return str(urlparse(url).hostname or "").strip()
    except Exception:
        return ""


def probe_vite_host_header(sandbox: Any, port: int, hostname: str) -> str:
    """Fetch the app as the public E2B Host header so Vite's check is visible."""
    host = (hostname or "").strip()
    if not host:
        return ""
    cmd = (
        "curl -sS -m 5 -A cocomputer-preview-check "
        f"-H {shlex.quote('Host: ' + host)} "
        f"http://127.0.0.1:{int(port)}/"
    )
    try:
        result = sandbox.run_command(cmd, timeout=10) or {}
    except Exception:
        logger.debug("preview host probe failed", exc_info=True)
        return ""
    return str(result.get("stdout") or "") + str(result.get("stderr") or "")


def find_vite_config_paths(sandbox: Any, *roots: str) -> list[str]:
    cleaned = [r.rstrip("/") for r in roots if isinstance(r, str) and r.strip() and r.strip() != "~"]
    if not cleaned:
        return []
    script = (
        "import os,sys\n"
        "names={'vite.config.ts','vite.config.js','vite.config.mts','vite.config.mjs','vite.config.cjs'}\n"
        "skip={'node_modules','.git','dist','.next','coverage'}\n"
        "seen=[]\n"
        "for root in sys.argv[1:]:\n"
        "  if not os.path.isdir(root): continue\n"
        "  root_depth=root.rstrip('/').count('/')\n"
        "  for dirpath, dirnames, filenames in os.walk(root):\n"
        "    depth=dirpath.rstrip('/').count('/')-root_depth\n"
        "    if depth>4:\n"
        "      dirnames[:] = []\n"
        "      continue\n"
        "    dirnames[:] = [d for d in dirnames if d not in skip]\n"
        "    for name in filenames:\n"
        "      if name in names:\n"
        "        path=os.path.join(dirpath, name)\n"
        "        if path not in seen:\n"
        "          seen.append(path)\n"
        "        if len(seen)>=8:\n"
        "          print('\\n'.join(seen)); raise SystemExit\n"
        "print('\\n'.join(seen))\n"
    )
    quoted_roots = " ".join(shlex.quote(root) for root in cleaned)
    try:
        result = sandbox.run_command(
            f"python3 -c {shlex.quote(script)} {quoted_roots}",
            timeout=25,
        ) or {}
    except Exception:
        logger.debug("vite config search failed", exc_info=True)
        return []
    out = str(result.get("stdout") or "").strip()
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip().endswith(tuple(VITE_CONFIG_NAMES))]


def ensure_vite_preview_hosts(sandbox: Any, *roots: str) -> list[str]:
    """Patch vite configs under the given roots. Returns paths that changed."""
    patched: list[str] = []
    for path in find_vite_config_paths(sandbox, *roots):
        try:
            source = sandbox.read_text_file(path)
        except Exception:
            logger.debug("could not read %s", path, exc_info=True)
            continue
        updated = patch_vite_config_source(source)
        if not updated:
            continue
        try:
            sandbox.write_text_file(path, updated)
        except Exception:
            logger.debug("could not write %s", path, exc_info=True)
            continue
        patched.append(path)
        logger.info("Patched Vite allowedHosts in %s", path)
    return patched


def kill_listening_port(sandbox: Any, port: int) -> None:
    port_number = int(port)
    sandbox.run_command(
        "sh -c "
        + shlex.quote(
            f"fuser -k {port_number}/tcp >/dev/null 2>&1 || true; "
            f"for pid in $(lsof -ti tcp:{port_number} 2>/dev/null); do kill -9 \"$pid\"; done; "
            "true"
        ),
        timeout=12,
    )


def restart_vite_dev_server(sandbox: Any, *, project_dir: str, port: int) -> None:
    """Kill whatever is on ``port`` and start Vite bound for the E2B preview."""
    directory = (project_dir or "").strip()
    if not directory or directory == "~":
        return
    port_number = int(port)
    kill_listening_port(sandbox, port_number)
    sandbox.run_command(
        f"npm run dev -- --host 0.0.0.0 --port {port_number}",
        timeout=15,
        background=True,
        cwd=directory,
    )


def vite_restart_port(sandbox: Any, requested_port: int) -> int:
    """Prefer the Vite port when an API proxy (e.g. Express :3001) is published."""
    requested = int(requested_port)
    if requested in _VITE_PORTS:
        return requested
    probe = getattr(sandbox, "probe_listening_port", None)
    if callable(probe):
        try:
            if probe(5173):
                return 5173
        except Exception:
            pass
    return requested


def prepare_vite_preview_for_e2b(
    sandbox: Any,
    *,
    port: int,
    workspace_path: str,
    public_url: str,
) -> dict[str, Any]:
    """Patch Vite configs and restart the dev server when the E2B host is blocked."""
    roots = [workspace_path]
    patched = ensure_vite_preview_hosts(sandbox, *roots)
    host = preview_hostname(public_url)
    body = probe_vite_host_header(sandbox, port, host)
    blocked = vite_host_is_blocked(body)
    if not patched and not blocked:
        return {"patched": [], "restarted": False, "blocked": False}

    restart_port = vite_restart_port(sandbox, port)
    project_dir = ""
    if patched:
        project_dir = str(PurePosixPath(patched[0]).parent)
    elif (workspace_path or "").strip():
        project_dir = workspace_path.rstrip("/")
    if not project_dir:
        return {"patched": patched, "restarted": False, "blocked": blocked}

    try:
        restart_vite_dev_server(sandbox, project_dir=project_dir, port=restart_port)
    except Exception:
        logger.debug("vite restart failed", exc_info=True)
        return {"patched": patched, "restarted": False, "blocked": blocked}
    return {
        "patched": patched,
        "restarted": True,
        "blocked": blocked,
        "restart_port": restart_port,
    }
