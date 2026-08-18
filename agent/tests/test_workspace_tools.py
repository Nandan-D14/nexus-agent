# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.sandbox import SandboxManager
from nexus.tools._context import (
    set_run_id,
    set_sandbox,
    set_session_id,
    set_workspace_path,
)
from nexus.orchestrator import NexusOrchestrator
from nexus.tools.web import (
    extract_html_title,
    parse_duckduckgo_results,
    scrape_web_page,
    web_search,
)
from nexus.tools.workspace import (
    derive_session_workspace_path,
    derive_workspace_path,
    initialize_task_state,
    list_workspace_files,
    prepare_task_workspace,
    read_task_state,
    read_workspace_file,
    reconcile_todo_list_at_turn_end,
    update_task_state,
    update_todo_item,
    write_todo_list,
    write_workspace_file,
)


class FakeSandbox:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.directories: set[str] = set()

    def ensure_directory(self, path: str) -> None:
        current = PurePosixPath(path.replace("\\", "/"))
        parts = current.parts
        built = ""
        for part in parts:
            if part == "/":
                built = "/"
            elif built in {"", "/"}:
                built = f"/{part}".replace("//", "/")
            else:
                built = f"{built}/{part}"
            self.directories.add(built.replace("\\", "/"))

    def write_text_file(self, path: str, content: str, *, append: bool = False) -> None:
        normalized = path.replace("\\", "/")
        parent = str(PurePosixPath(normalized).parent).replace("\\", "/")
        self.ensure_directory(parent)
        if append and normalized in self.files:
            self.files[normalized] += content
        else:
            self.files[normalized] = content

    def read_text_file(self, path: str) -> str:
        return self.files[path.replace("\\", "/")]

    def path_exists(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return normalized in self.files or normalized in self.directories

    def list_directory(self, path: str) -> list[dict[str, object]]:
        normalized = path.replace("\\", "/").rstrip("/")
        prefix = f"{normalized}/" if normalized else ""
        entries: dict[str, dict[str, object]] = {}
        for directory in self.directories:
            if not directory.startswith(prefix) or directory == normalized:
                continue
            remainder = directory[len(prefix):]
            if "/" in remainder:
                continue
            entries[remainder] = {
                "name": remainder,
                "path": directory,
                "is_dir": True,
                "size": 0,
            }
        for file_path, content in self.files.items():
            if not file_path.startswith(prefix):
                continue
            remainder = file_path[len(prefix):]
            if "/" in remainder:
                continue
            entries[remainder] = {
                "name": remainder,
                "path": file_path,
                "is_dir": False,
                "size": len(content.encode("utf-8")),
            }
        return sorted(entries.values(), key=lambda item: str(item["name"]))


class FakeHttpResponse:
    def __init__(self, *, url: str, status_code: int, text: str) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self.request = httpx.Request("GET", url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            reason = "Client error" if self.status_code < 500 else "Server error"
            raise httpx.HTTPStatusError(
                f"{reason} '{self.status_code}' for url '{self.url}'",
                request=self.request,
                response=self,
            )


class FakeAsyncClient:
    def __init__(self, response: FakeHttpResponse) -> None:
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None) -> FakeHttpResponse:
        return self.response


class WorkspaceHelperTests(TestCase):
    def test_derive_session_workspace_path_uses_session(self) -> None:
        path = derive_session_workspace_path("session123")
        self.assertEqual(path, "/home/user/CoComputer/Workspaces/session123")

    def test_derive_workspace_path_uses_session_and_run(self) -> None:
        path = derive_workspace_path("session123", "run456")
        self.assertEqual(path, "/home/user/CoComputer/Workspaces/session123/run456")

    def test_parse_duckduckgo_results_normalizes_basic_result_cards(self) -> None:
        html = """
        <div class="result">
          <a class="result__a" href="https://example.com/docs">Example Docs</a>
          <div class="result__snippet">Read the docs here.</div>
        </div>
        """
        results = parse_duckduckgo_results(html, max_results=5)
        self.assertEqual(
            results,
            [
                {
                    "title": "Example Docs",
                    "url": "https://example.com/docs",
                    "snippet": "Read the docs here.",
                }
            ],
        )

    def test_extract_html_title(self) -> None:
        self.assertEqual(extract_html_title("<html><title>Alpha Beta</title></html>"), "Alpha Beta")


class SandboxEnsureDirectoryTests(TestCase):
    def test_ensure_directory_falls_back_to_python(self) -> None:
        manager = SandboxManager()
        calls: list[str] = []

        def fake_run_command(command: str, timeout: int = 30, background: bool = False) -> dict:
            calls.append(command)
            if command.startswith("mkdir -p "):
                return {"stdout": "", "stderr": "", "exit_code": 1}
            return {"stdout": "", "stderr": "", "exit_code": 0}

        manager.run_command = fake_run_command  # type: ignore[method-assign]

        manager.ensure_directory("/home/user/CoComputer/Workspaces/session123")

        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].startswith("mkdir -p "))
        self.assertIn("python3 -c", calls[1])


class WorkspaceToolTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.sandbox = FakeSandbox()
        self.upload_patcher = patch("nexus.tools.workspace.upload_artifact_async", return_value=None)
        self.upload_patcher.start()
        self.session_token = set_session_id("session123")
        self.run_token = set_run_id("run456")
        self.workspace_token = set_workspace_path(
            "/home/user/CoComputer/Workspaces/session123/run456"
        )
        self.sandbox_token = set_sandbox(self.sandbox)

    async def asyncTearDown(self) -> None:
        self.upload_patcher.stop()
        for token in (
            self.sandbox_token,
            self.workspace_token,
            self.run_token,
            self.session_token,
        ):
            token.var.reset(token)

    async def test_prepare_task_workspace_creates_scaffold(self) -> None:
        result = await prepare_task_workspace("Investigate startup failure")
        detail = result["detail"]

        self.assertTrue(detail["created"])
        self.assertEqual(
            detail["workspace_path"],
            "/home/user/CoComputer/Workspaces/session123/run456",
        )
        self.assertIn("task.md", detail["touched_files"])
        self.assertIn("todo.md", detail["touched_files"])
        self.assertIn("notes.md", detail["touched_files"])
        self.assertIn("task_state.json", detail["touched_files"])
        self.assertEqual(detail["task_type"], "deep_research")
        self.assertEqual(detail["stage"], "intake")
        self.assertEqual(detail["review_status"], "pending")
        self.assertIn(detail["workspace_path"], self.sandbox.directories)
        self.assertIn(f"{detail['workspace_path']}/sources", self.sandbox.directories)
        self.assertIn(f"{detail['workspace_path']}/outputs", self.sandbox.directories)
        self.assertIn(f"{detail['workspace_path']}/todo.md", self.sandbox.files)

    async def test_task_state_tools_track_stage_review_evidence_and_artifacts(self) -> None:
        await prepare_task_workspace("Compare agent frameworks and write a report")
        init_result = await initialize_task_state(
            "Compare agent frameworks and write a report",
            task_type="deep_research",
            active_agent="deepresearcher",
        )
        self.assertEqual(init_result["metadata"]["task_type"], "deep_research")
        self.assertEqual(init_result["metadata"]["review_status"], "pending")

        update_result = await update_task_state(
            stage="reviewing",
            active_agent="research_reviewer_agent",
            review_status="passed",
            evidence=["sources/google_adk.md"],
            artifact_paths=["outputs/final.md"],
            summary="Reviewer passed the report.",
        )
        self.assertEqual(update_result["metadata"]["stage"], "reviewing")
        self.assertEqual(update_result["metadata"]["review_status"], "passed")
        self.assertEqual(update_result["metadata"]["evidence_count"], 1)
        self.assertEqual(update_result["metadata"]["artifact_count"], 1)

        state = (await read_task_state())["metadata"]["state"]
        self.assertEqual(state["active_agent"], "research_reviewer_agent")
        self.assertEqual(state["evidence"], ["sources/google_adk.md"])
        self.assertEqual(state["artifact_paths"], ["outputs/final.md"])
        self.assertEqual(state["trace"][-1]["summary"], "Reviewer passed the report.")

    async def test_todo_tools_write_and_update_stable_format(self) -> None:
        await prepare_task_workspace("Research")
        await write_todo_list(["Gather logs", "Compare docs"])
        await update_todo_item(2, "done", "Compared current docs")

        todo_text = (await read_workspace_file("todo.md"))["metadata"]["content"]
        self.assertIn("1. [pending] Gather logs", todo_text)
        self.assertIn("2. [done] Compare docs - Compared current docs", todo_text)

    async def test_reconcile_todo_list_marks_remaining_done_and_emits(self) -> None:
        from nexus.tools._context import set_send_json

        emitted: list[dict] = []

        async def capture(payload: dict) -> None:
            emitted.append(payload)

        send_token = set_send_json(capture)
        try:
            await prepare_task_workspace("Research")
            await write_todo_list(["Gather logs", "Compare docs", "Write report"])
            await update_todo_item(1, "done")
            await update_todo_item(2, "in_progress")

            items = await reconcile_todo_list_at_turn_end(mark_complete=True)
            self.assertEqual([item["status"] for item in items], ["done", "done", "done"])

            todo_text = (await read_workspace_file("todo.md"))["metadata"]["content"]
            self.assertIn("1. [done] Gather logs", todo_text)
            self.assertIn("2. [done] Compare docs", todo_text)
            self.assertIn("3. [done] Write report", todo_text)

            todo_events = [e for e in emitted if e.get("type") == "todo_list_updated"]
            self.assertTrue(todo_events)
            self.assertEqual(
                [item["status"] for item in todo_events[-1]["items"]],
                ["done", "done", "done"],
            )
        finally:
            send_token.var.reset(send_token)

    async def test_write_workspace_file_only_exposes_output_path_for_outputs(self) -> None:
        await prepare_task_workspace("Research")

        note_result = await write_workspace_file("notes.md", "hello", append=True)
        output_result = await write_workspace_file("outputs/final.md", "done")

        self.assertIn("workspace_file", note_result["metadata"])
        self.assertNotIn("output_path", note_result["metadata"])
        self.assertEqual(
            output_result["metadata"]["output_path"],
            "/home/user/CoComputer/Workspaces/session123/run456/outputs/final.md",
        )

    async def test_write_workspace_file_rejects_path_escape(self) -> None:
        await prepare_task_workspace("Research")
        result = await write_workspace_file("../escape.txt", "nope")
        self.assertEqual(
            result["summary"],
            "relative_path must stay inside the active workspace",
        )

    async def test_update_todo_item_returns_error_for_zero_index(self) -> None:
        await prepare_task_workspace("Research")
        await write_todo_list(["Gather logs", "Compare docs"])

        result = await update_todo_item(0, "in_progress")

        self.assertEqual(
            result["summary"],
            "item_index must be at least 1. Index is 1-based. Please retry with a valid index.",
        )

    async def test_update_todo_item_returns_not_found_when_todo_missing(self) -> None:
        result = await update_todo_item(1, "in_progress", "starting")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "NOT_FOUND")
        self.assertEqual(
            result["summary"],
            "todo.md does not exist yet. Call write_todo_list or prepare_task_workspace first.",
        )
        self.assertEqual(
            result["suggested_alternatives"],
            ["write_todo_list", "prepare_task_workspace"],
        )
        self.assertNotIn("Traceback", result["summary"])
        self.assertNotIn("pathlib.py", result["summary"])

    async def test_update_todo_item_sanitizes_sandbox_traceback(self) -> None:
        await prepare_task_workspace("Research")
        await write_todo_list(["Gather logs"])
        traceback_stderr = (
            "Traceback (most recent call last):\n"
            '  File "/usr/lib/python3.10/pathlib.py", line 1134, in read_text\n'
            "FileNotFoundError: [Errno 2] No such file or directory: 'todo.md'\n"
        )

        with patch.object(
            self.sandbox,
            "read_text_file",
            side_effect=RuntimeError(traceback_stderr),
        ):
            result = await update_todo_item(1, "done")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["summary"], "Failed to update the todo item.")
        self.assertNotIn("Traceback", result["summary"])
        self.assertNotIn("pathlib.py", result["summary"])

    async def test_read_workspace_file_returns_not_found_when_missing(self) -> None:
        result = await read_workspace_file("missing.md")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "NOT_FOUND")
        self.assertIn("missing.md does not exist in the workspace", result["summary"])
        self.assertEqual(
            result["suggested_alternatives"],
            ["list_workspace_files", "prepare_task_workspace"],
        )
        self.assertNotIn("Traceback", result["summary"])
        self.assertNotIn("pathlib.py", result["summary"])

    async def test_read_workspace_file_sanitizes_sandbox_traceback(self) -> None:
        await prepare_task_workspace("Research")
        traceback_stderr = (
            "Traceback (most recent call last):\n"
            '  File "/usr/lib/python3.10/pathlib.py", line 1134, in read_text\n'
            "FileNotFoundError: [Errno 2] No such file or directory: 'notes.md'\n"
        )

        with patch.object(
            self.sandbox,
            "read_text_file",
            side_effect=RuntimeError(traceback_stderr),
        ):
            result = await read_workspace_file("notes.md")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["summary"], "Failed to read the workspace file.")
        self.assertNotIn("Traceback", result["summary"])
        self.assertNotIn("pathlib.py", result["summary"])

    async def test_write_todo_list_returns_error_for_empty_items(self) -> None:
        await prepare_task_workspace("Research")

        result = await write_todo_list([])

        self.assertEqual(result["summary"], "Provide at least one todo item")

    async def test_list_workspace_files_returns_entries(self) -> None:
        await prepare_task_workspace("Research")
        await write_workspace_file("outputs/final.md", "done")
        listing = await list_workspace_files("outputs")

        self.assertEqual(listing["metadata"]["relative_path"], "outputs")
        self.assertEqual(len(listing["metadata"]["entries"]), 1)
        self.assertEqual(listing["metadata"]["entries"][0]["name"], "final.md")

    async def test_web_search_returns_error_payload_for_blank_query(self) -> None:
        await prepare_task_workspace("Research")

        result = await web_search("", max_results=5)

        self.assertEqual(result["summary"], "query is required")

    async def test_scrape_web_page_returns_error_payload_for_blocked_source(self) -> None:
        await prepare_task_workspace("Research")
        blocked_url = "https://www.reuters.com/markets/"
        response = FakeHttpResponse(url=blocked_url, status_code=401, text="Access denied")

        with patch("nexus.tools.web.httpx.AsyncClient", return_value=FakeAsyncClient(response)):
            result = await scrape_web_page(blocked_url, output_basename="reuters_markets")

        self.assertEqual(result["status"], "error")
        self.assertIn("blocked automated access", result["summary"])
        self.assertEqual(result["metadata"]["status_code"], 401)
        self.assertEqual(result["metadata"]["url"], blocked_url)

    async def test_scrape_web_page_fails_fast_on_http_504(self) -> None:
        await prepare_task_workspace("Research")
        url = "https://data.cityofnewyork.us/api/views/43nn-pn8j/rows.csv"
        response = FakeHttpResponse(url=url, status_code=504, text="Gateway Timeout")

        with patch("nexus.tools.web.httpx.AsyncClient", return_value=FakeAsyncClient(response)):
            result = await scrape_web_page(url, output_basename="nyc-restaurant-sample")

        self.assertEqual(result["status"], "error")
        self.assertIn("HTTP 504", result["summary"])
        self.assertNotIn("Stream removed", result["summary"])
        self.assertEqual(result["error_code"], "HTTP_504")

    async def test_scrape_web_page_hides_google_deadline_on_save(self) -> None:
        await prepare_task_workspace("Research")
        url = "https://example.com/page"
        response = FakeHttpResponse(url=url, status_code=200, text="<html><title>Ok</title></html>")

        with (
            patch("nexus.tools.web.httpx.AsyncClient", return_value=FakeAsyncClient(response)),
            patch(
                "nexus.tools.web.save_source_artifact",
                side_effect=RuntimeError("504 Stream removed (Deadline Exceeded)"),
            ),
        ):
            result = await scrape_web_page(url, output_basename="ok-page")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "TIMEOUT")
        self.assertNotIn("Stream removed", result["summary"])
        self.assertNotIn("Deadline Exceeded", result["summary"])


class WorkspaceRootRetryTests(IsolatedAsyncioTestCase):
    async def test_workspace_root_retries_and_succeeds(self) -> None:
        class FlakySandbox:
            def __init__(self) -> None:
                self.calls = 0

            def ensure_directory(self, path: str) -> None:
                self.calls += 1
                if self.calls < 3:
                    raise RuntimeError("temporary failure")

        orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
        orchestrator.session = type(
            "SessionStub",
            (),
            {
                "id": "session123",
                "sandbox": FlakySandbox(),
            },
        )()

        self.assertTrue(await orchestrator._ensure_session_workspace_root())
        self.assertEqual(orchestrator.session.sandbox.calls, 3)

    async def test_workspace_root_returns_false_after_exhausting_retries(self) -> None:
        class BrokenSandbox:
            def __init__(self) -> None:
                self.calls = 0

            def ensure_directory(self, path: str) -> None:
                self.calls += 1
                raise RuntimeError("permanent failure")

        orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
        orchestrator.session = type(
            "SessionStub",
            (),
            {
                "id": "session123",
                "sandbox": BrokenSandbox(),
            },
        )()

        self.assertFalse(await orchestrator._ensure_session_workspace_root())
        self.assertEqual(orchestrator.session.sandbox.calls, 3)

    async def test_prepare_workspace_for_turn_continues_when_root_bootstrap_fails(self) -> None:
        orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
        orchestrator.session = type("SessionStub", (), {"id": "session123"})()
        orchestrator._current_run_id = "run456"
        orchestrator._workspace_path = None
        orchestrator._bind_workspace_context = lambda: None
        orchestrator._ensure_session_workspace_root = AsyncMock(return_value=False)
        orchestrator._create_step = AsyncMock(return_value=None)
        orchestrator._complete_step = AsyncMock(return_value=None)
        orchestrator._fail_step = AsyncMock(return_value=None)

        with patch(
            "nexus.orchestrator.prepare_task_workspace",
            new=AsyncMock(
                return_value={
                    "workspace_path": "/home/user/CoComputer/Workspaces/session123/run456",
                    "created": True,
                    "touched_files": ["task.md"],
                }
            ),
        ):
            await orchestrator._prepare_workspace_for_turn("Research global news")
