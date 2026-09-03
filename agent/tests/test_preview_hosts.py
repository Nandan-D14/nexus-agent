# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Vite E2B preview host allowlisting."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools.preview_hosts import (
    command_starts_long_running_server,
    ensure_vite_preview_hosts,
    maybe_patch_dev_server_config,
    patch_vite_config_source,
    prepare_vite_preview_for_e2b,
    vite_config_allows_preview_hosts,
    vite_host_is_blocked,
)


DEFINE_CONFIG = """\
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
"""

SERVER_BLOCK = """\
export default defineConfig({
  server: {
    host: true,
    port: 5173,
  },
})
"""

RESTRICTED_HOSTS = """\
export default defineConfig({
  server: {
    allowedHosts: ['localhost'],
  },
})
"""

ALREADY_OPEN = """\
export default defineConfig({
  server: { host: true, allowedHosts: true },
})
"""

E2B_ARRAY = """\
export default defineConfig({
  server: { allowedHosts: ['.e2b.app'] },
})
"""


def test_command_starts_long_running_server() -> None:
    assert command_starts_long_running_server("npm run dev -- --host 0.0.0.0")
    assert command_starts_long_running_server("npx vite --host 0.0.0.0 --port 5173")
    assert command_starts_long_running_server("python3 -m http.server 8080")
    assert not command_starts_long_running_server("npm install")
    assert not command_starts_long_running_server("echo start the server")
    assert not command_starts_long_running_server("ls /workspace")
    assert not command_starts_long_running_server("npm run test")


def test_patch_define_config_inserts_server_block() -> None:
    patched = patch_vite_config_source(DEFINE_CONFIG)
    assert patched is not None
    assert "allowedHosts: true" in patched
    assert "host: true" in patched
    assert vite_config_allows_preview_hosts(patched)


def test_patch_existing_server_block() -> None:
    patched = patch_vite_config_source(SERVER_BLOCK)
    assert patched is not None
    assert "allowedHosts: true" in patched
    assert patched.index("server:") < patched.index("allowedHosts: true")


def test_patch_replaces_restricted_allowed_hosts() -> None:
    patched = patch_vite_config_source(RESTRICTED_HOSTS)
    assert patched is not None
    assert "allowedHosts: true" in patched
    assert "localhost" not in patched or "allowedHosts: ['localhost']" not in patched


def test_patch_skips_already_open_configs() -> None:
    assert patch_vite_config_source(ALREADY_OPEN) is None
    assert patch_vite_config_source(E2B_ARRAY) is None


def test_maybe_patch_only_touches_vite_config() -> None:
    assert maybe_patch_dev_server_config("src/App.tsx", "export default function App() {}") == (
        "export default function App() {}"
    )
    patched = maybe_patch_dev_server_config("vite.config.ts", DEFINE_CONFIG)
    assert "allowedHosts: true" in patched


def test_vite_host_is_blocked_detects_vite6_page() -> None:
    body = (
        'Blocked request. This host ("5173-abc.e2b.app") is not allowed.\n'
        "To allow this host, add \"5173-abc.e2b.app\" to `server.allowedHosts` in vite.config.js."
    )
    assert vite_host_is_blocked(body)
    assert not vite_host_is_blocked("<html><body>Hello</body></html>")


def test_ensure_vite_preview_hosts_writes_patched_config() -> None:
    files = {"/ws/vite.config.ts": DEFINE_CONFIG}
    commands: list[str] = []

    def run_command(command: str, timeout: int = 30, background: bool = False, cwd: str | None = None) -> dict:
        commands.append(command)
        if "os.walk" in command or "vite.config" in command:
            return {"exit_code": 0, "stdout": "/ws/vite.config.ts\n", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    sandbox = SimpleNamespace(
        run_command=run_command,
        read_text_file=lambda path: files[path],
        write_text_file=lambda path, content, append=False: files.__setitem__(path, content),
    )
    patched = ensure_vite_preview_hosts(sandbox, "/ws")
    assert patched == ["/ws/vite.config.ts"]
    assert "allowedHosts: true" in files["/ws/vite.config.ts"]


def test_prepare_restarts_when_host_is_blocked() -> None:
    files = {"/ws/vite.config.ts": DEFINE_CONFIG}
    calls: list[dict] = []

    def run_command(command: str, timeout: int = 30, background: bool = False, cwd: str | None = None) -> dict:
        calls.append({"command": command, "background": background, "cwd": cwd})
        if "os.walk" in command:
            return {"exit_code": 0, "stdout": "/ws/vite.config.ts\n", "stderr": ""}
        if "curl" in command:
            return {
                "exit_code": 0,
                "stdout": 'Blocked request. This host ("5173-abc.e2b.app") is not allowed.',
                "stderr": "",
            }
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    sandbox = SimpleNamespace(
        run_command=run_command,
        read_text_file=lambda path: files[path],
        write_text_file=lambda path, content, append=False: files.__setitem__(path, content),
        probe_listening_port=lambda port: port == 5173,
    )
    result = prepare_vite_preview_for_e2b(
        sandbox,
        port=5173,
        workspace_path="/ws",
        public_url="https://5173-abc.e2b.app",
    )
    assert result["patched"]
    assert result["restarted"] is True
    assert any(
        call["background"] is True and "npm run dev" in call["command"] for call in calls
    )
