# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools._context import (
    set_artifact_callback,
    set_run_id,
    set_sandbox,
    set_session_id,
    set_workspace_path,
    set_history_repository,
)
from nexus.tools.docs import (
    generate_pdf_report,
    generate_excel_report,
    generate_docx_report,
    generate_pptx_report,
    publish_html_artifact,
)


class FakeSandbox:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.commands_run: list[str] = []
        self.command_responses: dict[str, dict] = {}
        self.binary_files: dict[str, bytes] = {}

    def ensure_directory(self, path: str) -> None:
        pass

    def write_text_file(self, path: str, content: str, *, append: bool = False) -> None:
        self.files[path.replace("\\", "/")] = content

    def read_text_file(self, path: str) -> str:
        return self.files[path.replace("\\", "/")]

    def run_command(self, command: str, timeout: int = 30, background: bool = False) -> dict:
        self.commands_run.append(command)
        # Match standard python3 /tmp/gen_*.py command patterns
        for pattern, response in self.command_responses.items():
            if pattern in command:
                return response
        return {"stdout": '{"status": "success", "size": 1000, "engine": "try_weasyprint"}', "stderr": "", "exit_code": 0}

    def read_binary_file(self, path: str) -> bytes:
        normalized = path.replace("\\", "/")
        return self.binary_files.get(normalized, b"fake_binary_content")

    def path_exists(self, path: str) -> bool:
        return True


class DocsToolTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.sandbox = FakeSandbox()
        self.session_token = set_session_id("session123")
        self.run_token = set_run_id("run456")
        self.workspace_token = set_workspace_path(
            "/home/user/CoComputer/Workspaces/session123/run456"
        )
        self.sandbox_token = set_sandbox(self.sandbox)
        
        # Mock History Repository
        self.mock_history_repo = AsyncMock()
        self.mock_artifact = MagicMock()
        self.mock_artifact.artifact_id = "artifact_abc"
        self.mock_artifact.run_id = "run456"
        self.mock_artifact.session_id = "session123"
        self.mock_artifact.task_id = "session123"
        self.mock_artifact.kind = "html"
        self.mock_artifact.title = "Calculator"
        self.mock_artifact.preview = "Interactive HTML artifact ready."
        self.mock_artifact.created_at = None
        self.mock_artifact.source_step_id = None
        self.mock_artifact.path = "outputs/calculator.html"
        self.mock_artifact.url = "https://gcs/url"
        self.mock_artifact.metadata = {"render_mode": "iframe"}
        self.mock_history_repo.create_artifact.return_value = self.mock_artifact
        self.history_repo_token = set_history_repository(self.mock_history_repo)
        self.artifact_events: list[dict] = []
        self.artifact_callback_token = set_artifact_callback(
            lambda payload: self.artifact_events.append(payload)
        )

        # Patch GCS Uploads
        self.upload_patcher = patch("nexus.tools.docs.upload_artifact_async", return_value="https://gcs/url")
        self.mock_upload = self.upload_patcher.start()

    async def asyncTearDown(self) -> None:
        self.upload_patcher.stop()
        for token in (
            self.history_repo_token,
            self.artifact_callback_token,
            self.sandbox_token,
            self.workspace_token,
            self.run_token,
            self.session_token,
        ):
            token.var.reset(token)

    async def test_generate_pdf_report_success(self) -> None:
        result = await generate_pdf_report(
            title="Sample PDF Report",
            markdown_content="# Header\nSome markdown details",
            filename="my_test_report.pdf",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detail"]["filename"], "my_test_report.pdf")
        self.assertEqual(result["detail"]["artifact_id"], "artifact_abc")
        self.assertEqual(result["detail"]["url"], "https://gcs/url")
        
        # Verify commands executed in sandbox
        commands = self.sandbox.commands_run
        self.assertTrue(any("python3 /tmp/gen_pdf_" in cmd for cmd in commands))
        
        # Verify markdown content was written
        md_written = [k for k in self.sandbox.files.keys() if "_pdf_md_" in k]
        self.assertEqual(len(md_written), 1)
        self.assertIn("Some markdown details", self.sandbox.files[md_written[0]])

    async def test_generate_excel_report_success(self) -> None:
        result = await generate_excel_report(
            title="Sales Report",
            headers=["Month", "Revenue"],
            rows=[["Jan", "1000"], ["Feb", "1200"]],
            filename="sales.xlsx",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detail"]["filename"], "sales.xlsx")
        self.assertEqual(result["detail"]["artifact_id"], "artifact_abc")

        commands = self.sandbox.commands_run
        self.assertTrue(any("python3 /tmp/gen_xlsx_" in cmd for cmd in commands))
        script_files = [k for k in self.sandbox.files if "gen_xlsx_" in k]
        self.assertTrue(script_files)
        ast.parse(self.sandbox.files[script_files[0]])

    async def test_generate_docx_report_success(self) -> None:
        result = await generate_docx_report(
            title="Project Scope",
            markdown_content="# Overview\nScope of the new system.",
            filename="scope.docx",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detail"]["filename"], "scope.docx")
        self.assertEqual(result["detail"]["artifact_id"], "artifact_abc")

        # Verify docx generation was invoked
        commands = self.sandbox.commands_run
        self.assertTrue(any("python3 /tmp/gen_docx_" in cmd for cmd in commands))

    async def test_generate_pptx_report_success(self) -> None:
        result = await generate_pptx_report(
            title="Design Review",
            slides=[
                {"title": "Agenda", "bullets": ["Goals", "Timeline"]},
                {"title": "Next steps", "bullets": ["Ship preview"]},
            ],
            filename="review.pptx",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detail"]["filename"], "review.pptx")
        self.assertEqual(result["detail"]["artifact_id"], "artifact_abc")
        self.assertEqual(result["detail"]["preview_url"], "https://gcs/url")

        commands = self.sandbox.commands_run
        self.assertTrue(any("/tmp/_pptx_deps_" in cmd for cmd in commands))
        self.assertTrue(
            any(
                "python3 /tmp/gen_pptx_" in cmd and "_pptx_data_" in cmd and ".pptx" in cmd
                for cmd in commands
            )
        )
        script_files = [k for k in self.sandbox.files if "gen_pptx_" in k]
        self.assertTrue(script_files)
        script = self.sandbox.files[script_files[0]]
        self.assertIn("from pptx import Presentation", script)
        compile(script, script_files[0], "exec")
        self.assertIn("2DD4BF", script)
        self.assertIn("DATA_PATH", script)
        self.assertIn("modern-dark", script)
        self.assertNotIn("import importlib, subprocess, sys", script)

        data_files = [k for k in self.sandbox.files if "_pptx_data_" in k]
        self.assertTrue(data_files)
        payload = json.loads(self.sandbox.files[data_files[0]])
        self.assertEqual(payload["slides"][0]["layout"], "title")
        self.assertEqual(payload["slides"][0]["title"], "Design Review")
        create_kwargs = self.mock_history_repo.create_artifact.await_args.kwargs
        self.assertEqual(create_kwargs["kind"], "presentation")
        self.assertEqual(create_kwargs["metadata"]["preview_url"], "https://gcs/url")
        self.assertTrue(str(create_kwargs["metadata"]["preview_path"]).endswith(".html"))

    async def test_generate_pptx_report_requires_slides(self) -> None:
        result = await generate_pptx_report(title="Empty", slides=[], filename="empty.pptx")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "INVALID_SLIDES")

    async def test_publish_html_artifact_creates_preview_without_sandbox(self) -> None:
        result = await publish_html_artifact(
            title="Calculator",
            html="<button>1 + 1</button><script>console.log('ready')</script>",
            filename="calculator",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detail"]["artifact_id"], "artifact_abc")
        self.mock_upload.assert_awaited()
        upload_kwargs = self.mock_upload.await_args.kwargs
        self.assertEqual(upload_kwargs["relative_path"], "outputs/calculator.html")
        self.assertIn("<!doctype html>", upload_kwargs["content"].lower())
        self.mock_history_repo.create_artifact.assert_awaited()
        create_kwargs = self.mock_history_repo.create_artifact.await_args.kwargs
        self.assertEqual(create_kwargs["kind"], "html")
        self.assertEqual(create_kwargs["metadata"]["content_type"], "text/html; charset=utf-8")
        self.assertEqual(create_kwargs["metadata"]["render_mode"], "iframe")
        self.assertEqual(self.artifact_events[0]["kind"], "html")
