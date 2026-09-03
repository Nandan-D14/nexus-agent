# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.github_git import (
    TOKEN_PATH,
    install_github_git_credentials,
    resolve_workspace_path,
    run_sandbox_git,
    scrub_secret,
    validate_github_name,
)
from nexus.tools.integrations import github_clone_repo, github_create_repo, github_push


class FakeSandbox:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.files: dict[str, bytes | str] = {}
        self.stdout = ""
        self.stderr = ""
        self.exit_code = 0

    def ensure_directory(self, path: str) -> None:
        self.files[path] = "dir"

    def write_text_file(self, path: str, content: str, *, append: bool = False) -> None:
        self.files[path] = content

    def write_binary_file(self, path: str, content: bytes) -> None:
        self.files[path] = content

    def run_command(self, command: str, timeout: int = 30, background: bool = False) -> dict:
        self.commands.append(command)
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
        }


class GithubGitHelperTests(TestCase):
    def test_clone_command_does_not_embed_token(self) -> None:
        sandbox = FakeSandbox()
        token = "gho_secret_token_value"
        result = run_sandbox_git(
            sandbox,
            ["git", "clone", "https://github.com/acme/demo.git", "/ws/demo"],
            token=token,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("https://github.com/acme/demo.git", sandbox.commands[0])
        self.assertNotIn(token, sandbox.commands[0])
        self.assertNotIn(token, result["command"])

    def test_install_helper_keeps_token_out_of_shell_command(self) -> None:
        sandbox = FakeSandbox()
        token = "gho_secret_token_value"
        install_github_git_credentials(sandbox, token)
        self.assertEqual(sandbox.files[TOKEN_PATH], token.encode("utf-8"))
        joined = " ".join(sandbox.commands)
        self.assertNotIn(token, joined)
        self.assertIn("credential.https://github.com.helper", joined)

    def test_scrub_and_validate(self) -> None:
        self.assertEqual(scrub_secret("token=abc", "abc"), "token=***")
        self.assertIsNone(validate_github_name("my-app", kind="repository name"))
        self.assertIsNotNone(validate_github_name("../etc", kind="repository name"))
        path = resolve_workspace_path("/ws/s1", "app")
        self.assertEqual(path, "/ws/s1/app")
        with self.assertRaises(ValueError):
            resolve_workspace_path("/ws/s1", "../escape")


class GithubGitToolTests(IsolatedAsyncioTestCase):
    async def test_clone_requires_connection(self) -> None:
        with (
            patch("nexus.tools.integrations.get_history_repository", return_value=None),
            patch("nexus.tools.integrations.get_owner_id", return_value="user-1"),
        ):
            result = await github_clone_repo("acme", "demo")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "AUTH_REQUIRED")

    async def test_clone_runs_git_without_token_in_argv(self) -> None:
        sandbox = FakeSandbox()
        token = "gho_secret_token_value"

        async def fake_request(method, path, **kwargs):
            return {"data": {"login": "nanda", "email": "nanda@users.noreply.github.com"}}

        with (
            patch("nexus.tools.integrations._github_token", AsyncMock(return_value=token)),
            patch("nexus.tools.integrations._github_request", side_effect=fake_request),
            patch("nexus.tools.integrations.get_sandbox", return_value=sandbox),
            patch("nexus.tools.integrations.ensure_sandbox", AsyncMock()),
            patch(
                "nexus.tools.integrations.get_active_workspace_path",
                return_value="/ws/s1",
            ),
        ):
            result = await github_clone_repo("acme", "demo")

        self.assertEqual(result["status"], "success")
        clone_cmd = next(cmd for cmd in sandbox.commands if "clone" in cmd)
        self.assertIn("https://github.com/acme/demo.git", clone_cmd)
        self.assertNotIn(token, clone_cmd)
        self.assertEqual(result["metadata"]["path"], "/ws/s1/demo")

    async def test_create_repo_posts_to_github(self) -> None:
        async def fake_request(method, path, **kwargs):
            self.assertEqual(method, "POST")
            self.assertEqual(path, "/user/repos")
            self.assertEqual(kwargs["json"]["name"], "demo")
            self.assertTrue(kwargs["json"]["private"])
            return {
                "data": {
                    "full_name": "nanda/demo",
                    "html_url": "https://github.com/nanda/demo",
                    "clone_url": "https://github.com/nanda/demo.git",
                    "private": True,
                }
            }

        with (
            patch(
                "nexus.tools.integrations._github_token",
                AsyncMock(return_value="gho_secret_token_value"),
            ),
            patch("nexus.tools.integrations._github_request", side_effect=fake_request),
        ):
            result = await github_create_repo("demo", private=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            result["metadata"]["repository"]["html_url"],
            "https://github.com/nanda/demo",
        )

    async def test_push_without_remote_or_repo_name_errors(self) -> None:
        sandbox = FakeSandbox()
        sandbox.exit_code = 1
        sandbox.stderr = "not a git repository"

        async def fake_request(method, path, **kwargs):
            return {"data": {"login": "nanda"}}

        with (
            patch(
                "nexus.tools.integrations._github_token",
                AsyncMock(return_value="gho_secret"),
            ),
            patch("nexus.tools.integrations._github_request", side_effect=fake_request),
            patch("nexus.tools.integrations.get_sandbox", return_value=sandbox),
            patch("nexus.tools.integrations.ensure_sandbox", AsyncMock()),
            patch(
                "nexus.tools.integrations.get_active_workspace_path",
                return_value="/ws/s1",
            ),
        ):
            result = await github_push()

        self.assertEqual(result["status"], "error")
        self.assertIn(result["error_code"], {"MISSING_REMOTE", "GIT_FAILED", "EMPTY_REPO"})


class GithubAuthErrorTests(IsolatedAsyncioTestCase):
    async def test_github_401_asks_user_to_reconnect(self) -> None:
        from nexus.tools import integrations as integrations_module

        class FakeResponse:
            status_code = 401
            text = "Bad credentials"
            content = b"Bad credentials"

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, *args, **kwargs):
                return FakeResponse()

        with (
            patch(
                "nexus.tools.integrations._github_token",
                AsyncMock(return_value="gho_expired"),
            ),
            patch("nexus.tools.integrations.httpx.AsyncClient", return_value=FakeClient()),
        ):
            result = await integrations_module._github_request("GET", "/user")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "HTTP_401")
        self.assertFalse(result.get("retryable", True))
        self.assertIn("Connectors", result["summary"])
