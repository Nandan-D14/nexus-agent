# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Native SaaS connector tools for Gmail, Google Drive, GitHub, Tavily, and TinyFish."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from html import escape
from typing import Any

import httpx

from nexus.config import settings
from nexus.google_drive import decode_base64_upload, get_google_drive_client_from_context
from nexus.google_services import (
    GmailClient,
    TasksClient,
    CalendarClient,
    get_google_services_token_from_context,
)
from nexus.tools._context import (
    get_history_repository,
    get_owner_id,
    get_send_json,
    get_session_id,
)
from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


_GOOGLE_NOT_CONNECTED = "Google services are not connected."
_DRIVE_NOT_CONNECTED = "Google Drive is not connected for this user."
_GITHUB_NOT_CONNECTED = "GitHub is not connected for this user."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(value: str, *, fallback: str = "file") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_gmail_body(payload: Any) -> str:
    """Best-effort plain-text body from a Gmail message payload."""
    if not isinstance(payload, dict):
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body") or {}
    data = body.get("data") if isinstance(body, dict) else None
    if mime == "text/plain" and data:
        return _decode_b64url(data)
    for part in payload.get("parts") or []:
        text = _extract_gmail_body(part)
        if text:
            return text
    if data:
        return _decode_b64url(data)
    return ""


def _slim_gmail_message(message: Any, max_chars: int) -> dict[str, Any]:
    """Trim a raw Gmail message to key headers + capped text body.

    The raw Gmail API dict embeds the full base64 body and nested payload,
    which can be hundreds of KB and floods the model context. Return a compact,
    model-useful shape instead.
    """
    if not isinstance(message, dict):
        return {"raw": str(message)[:max_chars]}
    payload = message.get("payload") or {}
    wanted = {"from", "to", "cc", "subject", "date"}
    headers = {
        h.get("name", ""): h.get("value", "")
        for h in (payload.get("headers") or [])
        if isinstance(h, dict) and str(h.get("name", "")).lower() in wanted
    }
    body = _extract_gmail_body(payload)
    truncated = len(body) > max_chars
    return {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "labelIds": message.get("labelIds"),
        "snippet": message.get("snippet"),
        "headers": headers,
        "body": body[:max_chars],
        "truncated": truncated,
    }


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
        slim = _slim_gmail_message(message, settings.gmail_read_max_chars)
        return tool_success(
            f"Read message {message_id}",
            message=slim,
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


# ---------------------------------------------------------------------------
# Thesys Generative UI (C1)
# ---------------------------------------------------------------------------

async def _thesys_api_key() -> str | None:
    repo = get_history_repository()
    owner_id = get_owner_id()
    if repo is None or not owner_id:
        return None
    connection = await repo.get_integration_connection(owner_id, "thesys")
    api_key = connection.private.get("apiKey") if connection else None
    return api_key if isinstance(api_key, str) and api_key else None


def _extract_c1_response_content(raw_content: Any) -> str:
    """Normalize Thesys/OpenAI content shapes into a C1 response string."""
    if isinstance(raw_content, str):
        content = raw_content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:xml|html|c1|json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content).strip()
        if content.startswith("{") or content.startswith("["):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return content
            text = _extract_c1_response_content(parsed)
            return text or content
        return content
    if raw_content is None:
        return ""
    if isinstance(raw_content, list):
        parts: list[str] = []
        for part in raw_content:
            text = _extract_c1_response_content(part)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(raw_content, dict):
        for key in ("c1Response", "c1_response", "response", "text", "content", "output_text", "value"):
            value = raw_content.get(key)
            text = _extract_c1_response_content(value)
            if text:
                return text
        return json.dumps(raw_content, ensure_ascii=False)
    return str(raw_content)


# Props the Thesys SDK destructures and calls .map() on — they MUST be arrays.
_C1_ARRAY_PROPS: frozenset[str] = frozenset({
    "children",
    "items", "cards", "tiles", "metrics", "infoItems", "actions",
    "rows", "columns", "headers",
    "slides", "pages", "paragraphs", "fields",
    "data", "series", "labels", "datasets", "options", "points",
    "sources", "followUpText",
})


def _coerce_to_array(prop: str, value: Any) -> list[Any]:
    """Turn *value* into a list suitable for the given *prop* name."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            if isinstance(item, str) and prop == "sources":
                result.append({"title": item})
            else:
                result.append(_sanitize_json_structure(item))
        return result
    if isinstance(value, dict):
        return [_sanitize_json_structure(value)]
    if isinstance(value, str):
        if prop == "sources":
            return [{"title": value}]
        return [value]
    return []


def _sanitize_json_structure(data: Any) -> Any:
    """Ensure every prop the Thesys SDK calls ``.map()`` on is actually an array."""
    if isinstance(data, dict):
        new_dict: dict[str, Any] = {}
        for k, v in data.items():
            if k in _C1_ARRAY_PROPS:
                new_dict[k] = _coerce_to_array(k, v)
            else:
                new_dict[k] = _sanitize_json_structure(v)
        return new_dict
    if isinstance(data, list):
        return [_sanitize_json_structure(item) for item in data]
    return data


def _sanitize_c1_response(c1_response: str) -> str:
    """Patch common weak-model C1 mistakes that crash the SDK renderer."""
    normalized = c1_response.strip()

    def replace_content(match: re.Match) -> str:
        tag_open, inner_json, tag_close = match.groups()
        try:
            parsed = json.loads(inner_json.strip())
            sanitized_json = _sanitize_json_structure(parsed)
            return f"{tag_open}{json.dumps(sanitized_json, ensure_ascii=False, separators=(',', ':'))}{tag_close}"
        except Exception:
            return match.group(0)

    sanitized = re.sub(
        r'(<content\b[^>]*>)(.*?)(</content>)',
        replace_content,
        normalized,
        flags=re.DOTALL,
    )

    if sanitized.startswith("{") or sanitized.startswith("["):
        try:
            parsed = json.loads(sanitized)
            sanitized_json = _sanitize_json_structure(parsed)
            return json.dumps(sanitized_json, ensure_ascii=False, separators=(',', ':'))
        except Exception:
            pass

    sanitized = re.sub(
        r'("sources"\s*:\s*)(\{[^{}\[\]]*\})',
        r"\1[\2]",
        sanitized,
    )
    return sanitized


def _retry_after_seconds(response: httpx.Response) -> int | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        seconds = int(raw)
    except ValueError:
        return None
    return max(1, min(seconds, 300))


def _c1_custom_markdown(markdown: str) -> str:
    return f"<custommarkdown>{escape(markdown, quote=True)}</custommarkdown>"


async def _emit_generative_ui(
    *,
    component_type: str,
    title: str,
    c1_response: str,
) -> None:
    send_json = get_send_json()
    if send_json:
        await send_json({
            "type": "generative_ui",
            "component_type": component_type,
            "title": title,
            "component": c1_response,
        })

    repo = get_history_repository()
    session_id = get_session_id()
    if repo and session_id:
        try:
            await repo.append_message(
                session_id=session_id,
                owner_id=get_owner_id(),
                role="tool_result",
                source="generative_ui",
                text=json.dumps({
                    "component_type": component_type,
                    "title": title,
                    "component": c1_response,
                }),
            )
        except Exception:
            logger.warning("Failed to persist generative_ui component for session %s", session_id)


async def _emit_thesys_rate_limit_card(
    *,
    component_type: str,
    title: str,
    retry_after: int | None,
    detail: str = "",
) -> None:
    wait_text = f" Try again after about {retry_after} seconds." if retry_after else " Try again shortly."
    c1_response = _c1_custom_markdown(
        "### Thesys rate limit\n\n"
        "Thesys returned HTTP 429, so live UI generation could not complete."
        f"{wait_text}\n\n"
        f"**Thesys API Response:**\n```json\n{detail}\n```\n\n"
        "The app did call Thesys. No setup code was generated."
    )
    await _emit_generative_ui(
        component_type=component_type,
        title=title or "Thesys rate limit",
        c1_response=c1_response,
    )


@normalized_tool
async def render_ui(
    component_type: str,
    title: str,
    data: str,
    description: str = "",
) -> dict[str, Any]:
    """Generate an interactive Thesys C1 UI component (chart, table, form, dashboard, card, report) from data.

    Use this when Thesys is connected and the user asks to visualize data, compare items,
    create dashboards, or build interactive cards/forms. The component renders in the Workflow
    panel. If Thesys is not connected, fall back to publish_html_artifact.

    Args:
        component_type: Type of component — "chart", "table", "form", "dashboard", "card", or "report".
        title: A short descriptive title for the component.
        data: JSON string containing the data to visualize or use in the component.
        description: Optional additional context about what the component should show.

    Returns:
        NormalizedToolResult confirming the component was rendered.
    """
    api_key = await _thesys_api_key()
    if not api_key:
        return tool_error(
            "Thesys is not connected. Use publish_html_artifact for the visual instead, "
            "or ask the user to add their Thesys API key in the Connectors page.",
            error_code="AUTH_REQUIRED",
            suggested_alternatives=["publish_html_artifact"],
        )

    prompt = (
        f"Create a {component_type} titled '{title}'.\n\n"
        f"Data:\n{data}\n"
    )
    if description:
        prompt += f"\nAdditional context: {description}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            request_kwargs = {
                "headers": {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                "json": {
                    "model": settings.thesys_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return only valid Thesys C1 response markup. "
                                "Do not wrap it in Markdown code fences, JSON, or setup code. "
                                "Do not include citations or a sources prop."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
            }
            response = await client.post(
                "https://api.thesys.dev/v1/visualize/chat/completions",
                **request_kwargs,
            )
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                await asyncio.sleep(min(retry_after or 2, 60))
                response = await client.post(
                    "https://api.thesys.dev/v1/visualize/chat/completions",
                    **request_kwargs,
                )
                if response.status_code == 429:
                    retry_after = _retry_after_seconds(response) or retry_after
                    await _emit_thesys_rate_limit_card(
                        component_type=component_type,
                        title=title,
                        retry_after=retry_after,
                        detail=response.text,
                    )
                    return tool_error(
                        "Thesys API rate limited this request (HTTP 429).",
                        error_code="HTTP_429",
                        retry_after=retry_after,
                        rendered_fallback=True,
                    )
            if response.status_code >= 400:
                return tool_error(
                    f"Thesys API returned HTTP {response.status_code}: {response.text}",
                    error_code=f"HTTP_{response.status_code}",
                )

            result = response.json()
            raw_content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            c1_response = _sanitize_c1_response(_extract_c1_response_content(raw_content))

            if not c1_response.strip():
                return tool_error(
                    "Thesys C1 returned an empty response.",
                    error_code="EMPTY_RESPONSE",
                )

            await _emit_generative_ui(
                component_type=component_type,
                title=title,
                c1_response=c1_response,
            )

            return tool_success(
                f"Rendered {component_type}: {title}",
                component_type=component_type,
                title=title,
            )
    except Exception as exc:
        return tool_error(
            f"Thesys render_ui failed: {exc}",
        )
