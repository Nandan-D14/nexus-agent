# Proprietary and non-commercial use only.

"""File and directory I/O inside the sandbox."""

from __future__ import annotations

import base64
import json
import logging
import shlex

from nexus.sandbox import _coerce_exit_code
from nexus.sandbox_components.base import SandboxComponent

logger = logging.getLogger("nexus.sandbox")


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
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        data_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        mode = "ab" if append else "wb"
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            f"data = base64.b64decode('{data_b64}'); "
            "target = pathlib.Path(path); "
            "target.parent.mkdir(parents=True, exist_ok=True); "
            f"target.open('{mode}').write(data)"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to write file {path}")

    def write_binary_file(self, path: str, content: bytes) -> None:
        """Write binary content into a sandbox file."""
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
            raise RuntimeError(result.get("stderr") or f"Failed to read file {path}")
        return base64.b64decode(str(result.get("stdout") or ""))

    def read_text_file(self, path: str) -> str:
        """Read UTF-8 text from a sandbox file."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            "print(pathlib.Path(path).read_text(encoding='utf-8'))"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to read file {path}")
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
            raise RuntimeError(result.get("stderr") or f"Failed to list directory {path}")
        raw = str(result.get("stdout") or "").strip()
        if not raw:
            return []
        return list(json.loads(raw))
