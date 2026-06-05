# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Native SaaS connector tools for Gmail, Google Drive, GitHub, Tavily, and TinyFish."""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx

from nexus.google_drive import decode_base64_upload, get_google_drive_client_from_context
from nexus.google_services import (
    GmailClient,
    TasksClient,
    CalendarClient,
    get_google_services_token_from_context,
)
from nexus.tools._context import get_history_repository, get_owner_id
from nexus.tools.base import normalized_tool, tool_error, tool_success


_GOOGLE_NOT_CONNECTED = "Google services are not connected."
_DRIVE_NOT_CONNECTED = "Google Drive is not connected for this user."
_GITHUB_NOT_CONNECTED = "GitHub is not connected for this user."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(value: str, *, fallback: str = "file") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


async def _github_token() -> str | None:
    repo = get_history_repository()
    owner_id = get_owner_id()
    if repo is None or not owner_id:
        return None
    connection = await repo.get_integration_connection(owner_id, "github")
    token = connection.private.get("token") if connection else None
    return token if isinstance(token, str) and token else None


async def _github_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Make an authenticated GitHub API request. Returns raw result or tool_error."""
    token = await _github_token()
    if not token:
        return tool_error(_GITHUB_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        timeout=30.0,
        headers=headers,
    ) as client:
        response = await client.request(method, path, **kwargs)
        if response.status_code >= 400:
            return tool_error(
                f"GitHub API returned HTTP {response.status_code}.",
                error_code=f"HTTP_{response.status_code}",
                detail=response.text[:500],
            )
        return {"data": response.json() if response.content else {}}


async def _tavily_api_key() -> str | None:
    repo = get_history_repository()
    owner_id = get_owner_id()
    if repo is None or not owner_id:
        return None
    connection = await repo.get_integration_connection(owner_id, "tavily")
    api_key = connection.private.get("apiKey") if connection else None
    return api_key if isinstance(api_key, str) and api_key else None


async def _tinyfish_api_key() -> str | None:
    repo = get_history_repository()
    owner_id = get_owner_id()
    if repo is None or not owner_id:
        return None
    connection = await repo.get_integration_connection(owner_id, "tinyfish")
    api_key = connection.private.get("apiKey") if connection else None
    return api_key if isinstance(api_key, str) and api_key else None


# ---------------------------------------------------------------------------
# Gmail tools (3)
# ---------------------------------------------------------------------------

@normalized_tool
async def gmail_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search for emails in the user's Gmail account.

    Args:
        query: Search query (Gmail syntax like 'from:boss' or 'subject:report').
        max_results: Maximum number of messages to return.

    Returns:
        NormalizedToolResult with matching messages.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = GmailClient(token)
    try:
        results = await client.list_messages(query, max_results)
        messages = results.get("messages", [])
        return tool_success(
            f"Found {len(messages)} messages for '{query}'",
            messages=messages, message_count=len(messages),
        )
    except Exception as e:
        return tool_error(f"Gmail search failed: {e}")


@normalized_tool
async def gmail_read(message_id: str) -> dict[str, Any]:
    """Read a specific email message by ID.

    Args:
        message_id: The unique ID of the message to read.

    Returns:
        NormalizedToolResult with the full message content.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = GmailClient(token)
    try:
        message = await client.get_message(message_id)
        return tool_success(
            f"Read message {message_id}",
            message=message,
        )
    except Exception as e:
        return tool_error(f"Gmail read failed: {e}")


@normalized_tool
async def gmail_send(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send a new email message.

    Args:
        to: Recipient email address.
        subject: Subject line of the email.
        body: Plain text body of the email.

    Returns:
        NormalizedToolResult confirming the sent message.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = GmailClient(token)
    try:
        result = await client.send_message(to, subject, body)
        return tool_success(
            f"Sent email to {to}: {subject}",
            result=result, to=to, subject=subject,
        )
    except Exception as e:
        return tool_error(f"Gmail send failed: {e}")


# ---------------------------------------------------------------------------
# Google Tasks tools (2)
# ---------------------------------------------------------------------------

@normalized_tool
async def tasks_list(list_id: str = "@default") -> dict[str, Any]:
    """List tasks from a specific Google Tasks list.

    Args:
        list_id: The ID of the task list (defaults to '@default').

    Returns:
        NormalizedToolResult with task items.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = TasksClient(token)
    try:
        tasks = await client.list_tasks(list_id)
        items = tasks.get("items", [])
        return tool_success(
            f"Listed {len(items)} tasks",
            tasks=items, task_count=len(items),
        )
    except Exception as e:
        return tool_error(f"Tasks list failed: {e}")


@normalized_tool
async def tasks_create(title: str, notes: str = "", due: str | None = None) -> dict[str, Any]:
    """Create a new task in the default Google Tasks list.

    Args:
        title: Title of the task.
        notes: Optional description or notes for the task.
        due: Optional due date in RFC 3339 format (e.g., '2026-05-01T12:00:00Z').

    Returns:
        NormalizedToolResult with the created task.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = TasksClient(token)
    try:
        task = await client.create_task(title, notes, due)
        return tool_success(
            f"Created task: {title}",
            task=task,
        )
    except Exception as e:
        return tool_error(f"Tasks create failed: {e}")


# ---------------------------------------------------------------------------
# Google Calendar tools (2)
# ---------------------------------------------------------------------------

@normalized_tool
async def calendar_list(max_results: int = 10) -> dict[str, Any]:
    """List upcoming events from the user's primary Google Calendar.

    Args:
        max_results: Maximum number of events to return.

    Returns:
        NormalizedToolResult with upcoming events.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = CalendarClient(token)
    try:
        events = await client.list_events(max_results=max_results)
        items = events.get("items", [])
        return tool_success(
            f"Listed {len(items)} upcoming events",
            events=items, event_count=len(items),
        )
    except Exception as e:
        return tool_error(f"Calendar list failed: {e}")


@normalized_tool
async def calendar_create(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
) -> dict[str, Any]:
    """Create a new event in the user's primary Google Calendar.

    Args:
        summary: Title of the event.
        start_time: Start time in RFC 3339 format.
        end_time: End time in RFC 3339 format.
        description: Optional detailed description.
        location: Optional physical or virtual location.

    Returns:
        NormalizedToolResult with the created event.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return tool_error(_GOOGLE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    client = CalendarClient(token)
    try:
        event = await client.create_event(summary, start_time, end_time, description, location)
        return tool_success(
            f"Created event: {summary} ({start_time} - {end_time})",
            event=event,
        )
    except Exception as e:
        return tool_error(f"Calendar create failed: {e}")


# ---------------------------------------------------------------------------
# Google Drive tools (4)
# ---------------------------------------------------------------------------

@normalized_tool
async def search_drive(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search the connected user's Google Drive files.

    Args:
        query: Search text to match against Drive file names or content.
        max_results: Maximum number of files to return.

    Returns:
        NormalizedToolResult with matching Drive files.
    """
    client = await get_google_drive_client_from_context()
    if not client:
        return tool_error(_DRIVE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    escaped_query = (query or "").replace("'", "\\'")
    q = f"fullText contains '{escaped_query}' and trashed = false"
    body = await client.list_files(
        params={
            "q": q,
            "pageSize": max(1, min(int(max_results or 10), 25)),
            "fields": "files(id,name,mimeType,webViewLink,modifiedTime,size)",
        }
    )
    files = body.get("files", [])
    return tool_success(
        f"Found {len(files)} Drive files for '{query}'",
        files=files, file_count=len(files),
    )


@normalized_tool
async def read_drive_file(file_id: str, max_chars: int = 12000) -> dict[str, Any]:
    """Read text content from a Google Drive file or exported Google Doc.

    Args:
        file_id: The Drive file ID to read.
        max_chars: Maximum characters to return (default 12000).

    Returns:
        NormalizedToolResult with file content and metadata.
    """
    client = await get_google_drive_client_from_context()
    if not client:
        return tool_error(_DRIVE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    meta = await client.get_file(file_id, params={"fields": "id,name,mimeType,webViewLink"})
    mime_type = str(meta.get("mimeType", ""))
    text = await client.read_text(file_id, mime_type)
    limit = max(1000, min(int(max_chars or 12000), 50000))
    truncated = len(text) > limit
    return tool_success(
        f"Read Drive file: {meta.get('name', file_id)} ({len(text)} chars{'...' if truncated else ''})",
        file=meta,
        content=text[:limit],
        truncated=truncated,
    )


@normalized_tool
async def create_drive_doc(title: str, content: str) -> dict[str, Any]:
    """Create a Google Docs document in the connected user's Drive.

    Args:
        title: Document title.
        content: Document content (plain text or markdown).

    Returns:
        NormalizedToolResult with the created document metadata.
    """
    client = await get_google_drive_client_from_context()
    if not client:
        return tool_error(_DRIVE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    created = await client.create_google_doc(title=title, content=content)
    return tool_success(
        f"Created Google Doc: {title}",
        file=created,
    )


@normalized_tool
async def upload_drive_file(filename: str, content_base64: str, mime_type: str = "application/octet-stream") -> dict[str, Any]:
    """Upload a base64-encoded file to the connected user's Google Drive.

    Args:
        filename: Name for the uploaded file.
        content_base64: Base64-encoded file content.
        mime_type: MIME type of the file.

    Returns:
        NormalizedToolResult with uploaded file metadata.
    """
    client = await get_google_drive_client_from_context()
    if not client:
        return tool_error(_DRIVE_NOT_CONNECTED, error_code="AUTH_REQUIRED")
    try:
        raw = await decode_base64_upload(content_base64)
    except Exception:
        return tool_error("content_base64 must be valid base64.", error_code="INVALID_INPUT")
    uploaded = await client.upload_bytes(
        filename=filename,
        content=raw,
        mime_type=mime_type or "application/octet-stream",
    )
    return tool_success(
        f"Uploaded {filename} to Drive",
        file=uploaded,
    )


# ---------------------------------------------------------------------------
# GitHub tools (5)
# ---------------------------------------------------------------------------

@normalized_tool
async def github_search_repos(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search GitHub repositories visible to the connected GitHub token.

    Args:
        query: Search query string.
        max_results: Maximum number of repositories to return.

    Returns:
        NormalizedToolResult with matching repositories.
    """
    result = await _github_request(
        "GET",
        "/search/repositories",
        params={"q": query, "per_page": max(1, min(int(max_results or 10), 25))},
    )
    if result.get("status") == "error":
        return result
    items = result["data"].get("items", [])
    repos = [
        {
            "full_name": item.get("full_name"),
            "description": item.get("description"),
            "html_url": item.get("html_url"),
            "stars": item.get("stargazers_count"),
            "language": item.get("language"),
        }
        for item in items
    ]
    return tool_success(
        f"Found {len(repos)} repos for '{query}'",
        repositories=repos, repo_count=len(repos),
    )


@normalized_tool
async def github_read_file(owner: str, repo: str, path: str, ref: str = "main", max_chars: int = 20000) -> dict[str, Any]:
    """Read a file from a GitHub repository visible to the connected token.

    Args:
        owner: Repository owner.
        repo: Repository name.
        path: File path within the repository.
        ref: Git ref (branch, tag, or commit SHA). Default 'main'.
        max_chars: Maximum characters to return.

    Returns:
        NormalizedToolResult with file content and metadata.
    """
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}",
        params={"ref": ref},
    )
    if result.get("status") == "error":
        return result
    data = result["data"]
    encoded = data.get("content", "")
    try:
        content = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        return tool_error("GitHub returned file content that could not be decoded.")
    limit = max(1000, min(int(max_chars or 20000), 50000))
    truncated = len(content) > limit
    return tool_success(
        f"Read {owner}/{repo}/{path} ({len(content)} chars{'...' if truncated else ''})",
        file={
            "name": data.get("name"),
            "path": data.get("path"),
            "sha": data.get("sha"),
            "html_url": data.get("html_url"),
        },
        content=content[:limit],
        truncated=truncated,
    )


@normalized_tool
async def github_list_issues(owner: str, repo: str, state: str = "open", max_results: int = 20) -> dict[str, Any]:
    """List GitHub issues for a repository visible to the connected token.

    Args:
        owner: Repository owner.
        repo: Repository name.
        state: Issue state filter ('open', 'closed', 'all').
        max_results: Maximum number of issues to return.

    Returns:
        NormalizedToolResult with matching issues.
    """
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": max(1, min(int(max_results or 20), 50))},
    )
    if result.get("status") == "error":
        return result
    issues = [
        {
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "html_url": item.get("html_url"),
            "user": (item.get("user") or {}).get("login"),
        }
        for item in result["data"]
        if "pull_request" not in item
    ]
    return tool_success(
        f"Listed {len(issues)} issues in {owner}/{repo}",
        issues=issues, issue_count=len(issues),
    )


@normalized_tool
async def github_create_issue(owner: str, repo: str, title: str, body: str = "", labels: list[str] | None = None) -> dict[str, Any]:
    """Create a GitHub issue in a repository visible to the connected token.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: Issue title.
        body: Issue body/description.
        labels: Optional list of label names.

    Returns:
        NormalizedToolResult with the created issue.
    """
    result = await _github_request(
        "POST",
        f"/repos/{owner}/{repo}/issues",
        json={"title": title, "body": body, "labels": labels or []},
    )
    if result.get("status") == "error":
        return result
    data = result["data"]
    return tool_success(
        f"Created issue #{data.get('number')}: {title}",
        issue={
            "number": data.get("number"),
            "title": data.get("title"),
            "html_url": data.get("html_url"),
            "state": data.get("state"),
        },
    )


@normalized_tool
async def github_summarize_pr(owner: str, repo: str, pull_number: int) -> dict[str, Any]:
    """Fetch pull request metadata and changed files so the agent can summarize it.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: PR number.

    Returns:
        NormalizedToolResult with PR details and changed files.
    """
    pr = await _github_request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}")
    if pr.get("status") == "error":
        return pr
    files = await _github_request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}/files")
    if files.get("status") == "error":
        return files
    pr_data = pr["data"]
    file_data = files["data"]
    changed_files = [
        {
            "filename": item.get("filename"),
            "status": item.get("status"),
            "additions": item.get("additions"),
            "deletions": item.get("deletions"),
            "patch": item.get("patch", "")[:4000],
        }
        for item in file_data[:50]
    ]
    return tool_success(
        f"PR #{pull_number}: {pr_data.get('title', '')} ({len(changed_files)} files changed)",
        pull_request={
            "number": pr_data.get("number"),
            "title": pr_data.get("title"),
            "state": pr_data.get("state"),
            "html_url": pr_data.get("html_url"),
            "body": pr_data.get("body"),
        },
        files=changed_files,
    )


# ---------------------------------------------------------------------------
# Tavily search (1)
# ---------------------------------------------------------------------------

@normalized_tool
async def tavily_search(query: str, search_depth: str = "basic", max_results: int = 5, include_answer: bool = True) -> dict[str, Any]:
    """Search the web using Tavily AI search engine.

    Args:
        query: The search query.
        search_depth: Search depth — "basic" or "advanced".
        max_results: Maximum number of search results to return.
        include_answer: Whether to include an AI-generated answer.

    Returns:
        NormalizedToolResult with search results and optional AI answer.
    """
    api_key = await _tavily_api_key()
    if not api_key:
        return tool_error(
            "Tavily is not connected for this user.",
            error_code="AUTH_REQUIRED",
            suggested_alternatives=["web_search"],
        )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": max(1, min(int(max_results or 5), 20)),
                    "include_answer": include_answer,
                },
            )
            if response.status_code >= 400:
                return tool_error(
                    f"Tavily API returned HTTP {response.status_code}.",
                    error_code=f"HTTP_{response.status_code}",
                    suggested_alternatives=["web_search"],
                    detail=response.text[:500],
                )
            data = response.json()
            results = [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                }
                for item in data.get("results", [])
            ]
            return tool_success(
                f"Tavily found {len(results)} results for '{query}'",
                answer=data.get("answer"),
                results=results,
                result_count=len(results),
            )
    except Exception as exc:
        return tool_error(
            f"Tavily search failed: {exc}",
            suggested_alternatives=["web_search"],
        )


# ---------------------------------------------------------------------------
# TinyFish web agent (1)
# ---------------------------------------------------------------------------

@normalized_tool
async def tinyfish_web_agent(url: str, goal: str) -> dict[str, Any]:
    """Use TinyFish to automate a browser task on a real website using a natural language goal.

    Args:
        url: The starting URL of the website.
        goal: A natural language description of what to accomplish.

    Returns:
        NormalizedToolResult with the automation result.
    """
    api_key = await _tinyfish_api_key()
    if not api_key:
        return tool_error(
            "Tinyfish is not connected for this user.",
            error_code="AUTH_REQUIRED",
            suggested_alternatives=["open_browser", "playwright_navigate"],
        )
    try:
        async with httpx.AsyncClient(
            timeout=120.0,
            headers={"X-API-Key": api_key},
        ) as client:
            response = await client.post(
                "https://agent.tinyfish.ai/v1/automation/run",
                json={"url": url, "goal": goal},
            )
            if response.status_code >= 400:
                return tool_error(
                    f"Tinyfish API returned HTTP {response.status_code}.",
                    error_code=f"HTTP_{response.status_code}",
                    suggested_alternatives=["open_browser"],
                    detail=response.text[:500],
                )
            data = response.json()
            return tool_success(
                f"TinyFish completed: {goal}",
                run_id=data.get("run_id"),
                task_status=data.get("status"),
                result=data.get("result"),
                error=data.get("error"),
            )
    except Exception as exc:
        return tool_error(
            f"Tinyfish web agent failed: {exc}",
            suggested_alternatives=["open_browser"],
        )
