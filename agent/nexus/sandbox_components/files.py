# Proprietary and non-commercial use only.

"""File and directory I/O inside the sandbox."""

from __future__ import annotations

import base64
import json
import logging
import shlex

from nexus.sandbox import SandboxDeadError, _coerce_exit_code
from nexus.sandbox_components.base import SandboxComponent

logger = logging.getLogger("nexus.sandbox")

TEXT_PREVIEW_MAX_BYTES = 2 * 1024 * 1024
TEXT_PREVIEW_EXTENSIONS = frozenset(
    {
        "py",
        "ts",
        "tsx",
        "js",
        "jsx",
        "mjs",
        "cjs",
        "json",
        "md",
        "mdx",
        "html",
        "htm",
        "css",
        "scss",
        "sass",
        "less",
        "sh",
        "bash",
        "zsh",
        "yml",
        "yaml",
        "toml",
        "ini",
        "cfg",
        "conf",
        "txt",
        "xml",
        "svg",
        "csv",
        "sql",
        "go",
        "rs",
        "java",
        "kt",
        "rb",
        "php",
        "c",
        "h",
        "cpp",
        "hpp",
        "cs",
        "swift",
        "vue",
        "svelte",
        "graphql",
        "prisma",
    }
)
_TEXT_PREVIEW_BASENAMES = frozenset(
    {
        "dockerfile",
        "makefile",
        "readme",
        "license",
        "procfile",
        "gemfile",
        "rakefile",
    }
)


def is_previewable_text_file(name: str, size: int | None = None) -> bool:
    """Return True when a workspace file is safe to open as text in the editor."""
    if size is not None and (size < 0 or size > TEXT_PREVIEW_MAX_BYTES):
        return False
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not base:
        return False
    lowered = base.lower()
    if lowered in _TEXT_PREVIEW_BASENAMES:
        return True
    if base.startswith(".") and "." not in base[1:]:
        return True
    if "." not in base:
        return False
    ext = base.rsplit(".", 1)[-1].lower()
    return ext in TEXT_PREVIEW_EXTENSIONS


def raise_sandbox_io_error(path: str, stderr: str | None, *, action: str) -> None:
    """Raise a short I/O error; never forward raw sandbox Python tracebacks."""
    text = (stderr or "").strip()
    lowered = text.lower()
    missing = (
        "filenotfounderror" in lowered
        or "no such file or directory" in lowered
        or "enosent" in lowered
    )
    if missing:
        noun = "Directory" if action.startswith("list") else "File"
        raise FileNotFoundError(f"{noun} not found: {path}")
    raise RuntimeError(f"Failed to {action} {path}")


class SandboxFiles(SandboxComponent):

    def ensure_directory(self, path: str) -> None:
        """Create a directory and its parents inside the sandbox."""
        safe_path = shlex.quote(path)
        result = self.run_command(f"mkdir -p {safe_path}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) == 0:
            return

        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            "pathlib.Path(path).mkdir(parents=True, exist_ok=True)"
        )
        fallback = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(fallback.get("exit_code", -1)) == 0:
            logger.warning(
                "ensure_directory recovered via python fallback for %s after mkdir failed "
                "(exit=%s, stderr=%s, stdout=%s)",
                path,
                result.get("exit_code"),
                result.get("stderr") or "",
                result.get("stdout") or "",
            )
            return

        logger.error(
            "ensure_directory failed for %s: mkdir exit=%s stderr=%s stdout=%s; "
            "python fallback exit=%s stderr=%s stdout=%s",
            path,
            result.get("exit_code"),
            result.get("stderr") or "",
            result.get("stdout") or "",
            fallback.get("exit_code"),
            fallback.get("stderr") or "",
            fallback.get("stdout") or "",
        )
        raise RuntimeError(
            fallback.get("stderr")
            or result.get("stderr")
            or f"Failed to create directory {path}"
        )

    def write_text_file(self, path: str, content: str, *, append: bool = False) -> None:
        """Write UTF-8 text into a sandbox file."""
        payload = content.encode("utf-8")
        if append:
            try:
                payload = self.read_binary_file(path) + payload
            except FileNotFoundError:
                pass
        self.write_binary_file(path, payload)

    def write_binary_file(self, path: str, content: bytes) -> None:
        """Write binary content into a sandbox file via the E2B files API."""
        self._require_sandbox()
        files = getattr(self._sandbox, "files", None)
        write = getattr(files, "write", None) if files is not None else None
        if not callable(write):
            self._write_binary_file_via_python(path, content)
            return
        try:
            write(path, content, request_timeout=120)
            return
        except SandboxDeadError:
            raise
        except Exception as exc:
            self._raise_if_dead(exc)
            logger.warning(
                "E2B files.write failed for %s (%d bytes): %s",
                path,
                len(content),
                exc,
            )
            if len(content) <= 32 * 1024:
                self._write_binary_file_via_python(path, content)
                return
            raise RuntimeError(f"Failed to write file {path}") from exc

    def _write_binary_file_via_python(self, path: str, content: bytes) -> None:
        """Fallback writer for tiny files when the E2B files API is unavailable."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        data_b64 = base64.b64encode(content).decode("ascii")
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            f"data = base64.b64decode('{data_b64}'); "
            "target = pathlib.Path(path); "
            "target.parent.mkdir(parents=True, exist_ok=True); "
            "target.write_bytes(data)"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=60)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to write file {path}")

    def read_binary_file(self, path: str) -> bytes:
        """Read binary content from a sandbox file."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib, sys; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            "sys.stdout.write(base64.b64encode(pathlib.Path(path).read_bytes()).decode('ascii'))"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=60)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise_sandbox_io_error(path, result.get("stderr"), action="read file")
        return base64.b64decode(str(result.get("stdout") or ""))

    def read_text_file(self, path: str, *, max_chars: int = 0) -> str:
        """Read UTF-8 text from a sandbox file.

        ``max_chars`` truncates inside the sandbox rather than after transfer,
        so an oversized file never has to fit through stdout in the first place.
        """
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        limit = max(0, int(max_chars))
        script = (
            "import base64, pathlib, sys; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            f"limit = {limit}; "
            "text = pathlib.Path(path).read_text(encoding='utf-8'); "
            "sys.stdout.write(text if limit <= 0 else text[:limit])"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise_sandbox_io_error(path, result.get("stderr"), action="read file")
        return str(result.get("stdout") or "")

    def path_exists(self, path: str) -> bool:
        """Return True when the given sandbox path exists."""
        safe_path = shlex.quote(path)
        result = self.run_command(f"test -e {safe_path}", timeout=15)
        return _coerce_exit_code(result.get("exit_code", -1)) == 0

    def list_directory(self, path: str) -> list[dict[str, object]]:
        """Return a shallow directory listing for the given sandbox path."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, json, pathlib; "
            f"path = pathlib.Path(base64.b64decode('{path_b64}').decode('utf-8')); "
            "exists = path.exists(); "
            "iterable = sorted(path.iterdir(), key=lambda item: item.name.lower()) if exists and path.is_dir() else []; "
            "entries = [{'name': item.name, 'path': str(item), 'is_dir': item.is_dir(), 'size': item.stat().st_size if item.exists() else 0} for item in iterable]; "
            "print(json.dumps(entries))"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise_sandbox_io_error(path, result.get("stderr"), action="list directory")
        raw = str(result.get("stdout") or "").strip()
        if not raw:
            return []
        return list(json.loads(raw))

    def list_tree(
        self,
        path: str,
        *,
        max_depth: int = 8,
        max_entries: int = 2000,
    ) -> list[dict[str, object]]:
        """Return a recursive directory listing relative to ``path``.

        Each entry: ``name``, ``relative_path``, ``is_dir``, ``size``.
        Skips common noise dirs and caps depth/count for UI safety.
        """
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = f"""
import base64, json, pathlib
root = pathlib.Path(base64.b64decode('{path_b64}').decode('utf-8'))
max_depth = {int(max_depth)}
max_entries = {int(max_entries)}
skip = {{'__pycache__', '.git', 'node_modules', '.venv', 'venv', '.tox', '.mypy_cache', '.pytest_cache'}}
entries = []

def walk(current, depth):
    if len(entries) >= max_entries or depth > max_depth:
        return
    try:
        children = sorted(current.iterdir(), key=lambda i: (not i.is_dir(), i.name.lower()))
    except (OSError, PermissionError):
        return
    for item in children:
        if len(entries) >= max_entries:
            break
        name = item.name
        if name in skip or name.startswith('.'):
            continue
        try:
            is_dir = item.is_dir()
            size = 0 if is_dir else (item.stat().st_size if item.exists() else 0)
        except (OSError, PermissionError):
            continue
        rel = str(item.relative_to(root)).replace('\\\\', '/')
        entries.append({{'name': name, 'relative_path': rel, 'is_dir': is_dir, 'size': size}})
        if is_dir:
            walk(item, depth + 1)

if root.exists() and root.is_dir():
    walk(root, 0)
print(json.dumps(entries))
"""
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=60)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to list tree {path}")
        raw = str(result.get("stdout") or "").strip()
        if not raw:
            return []
        return list(json.loads(raw))

    def archive_tree(self, path: str) -> bytes:
        """Create a gzip tar of ``path``, skipping bulky dependency dirs."""
        dest = "/tmp/cocomputer-workspace.tgz"
        quoted_root = shlex.quote(path)
        quoted_dest = shlex.quote(dest)
        command = (
            f"tar -C {quoted_root} "
            "--exclude=node_modules --exclude=.git --exclude=.venv --exclude=venv "
            "--exclude=__pycache__ --exclude=.next --exclude=dist --exclude=build "
            f"-czf {quoted_dest} ."
        )
        result = self.run_command(command, timeout=120)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to archive {path}")
        return self.read_binary_file(dest)
