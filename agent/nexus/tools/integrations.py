"""Native SaaS connector tools for Google Drive and GitHub."""

from __future__ import annotations

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


def _tool_error(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "error": message}
    payload.update(extra)
    return payload


async def gmail_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search for emails in the user's Gmail account.

    Args:
        query: Search query (Gmail syntax like 'from:boss' or 'subject:report').
        max_results: Maximum number of messages to return.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = GmailClient(token)
    try:
        results = await client.list_messages(query, max_results)
        return {"status": "success", "messages": results.get("messages", [])}
    except Exception as e:
        return _tool_error(f"Gmail search failed: {e}")


async def gmail_read(message_id: str) -> dict[str, Any]:
    """Read a specific email message by ID.

    Args:
        message_id: The unique ID of the message to read.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = GmailClient(token)
    try:
        message = await client.get_message(message_id)
        return {"status": "success", "message": message}
    except Exception as e:
        return _tool_error(f"Gmail read failed: {e}")


async def gmail_send(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send a new email message.

    Args:
        to: Recipient email address.
        subject: Subject line of the email.
        body: Plain text body of the email.
    """
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = GmailClient(token)
    try:
        result = await client.send_message(to, subject, body)
        return {"status": "success", "result": result}
    except Exception as e:
        return _tool_error(f"Gmail send failed: {e}")


async def tasks_list(list_id: str = "@default") -> dict[str, Any]:
    """List tasks from a specific Google Tasks list.

    Args:
        list_id: The ID of the task list (defaults to '@default').
    """
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = TasksClient(token)
    try:
        tasks = await client.list_tasks(list_id)
        return {"status": "success", "tasks": tasks.get("items", [])}
    except Exception as e:
        return _tool_error(f"Tasks list failed: {e}")


async def tasks_create(title: str, notes: str = "", due: str | None = None) -> dict[str, Any]:
    """Create a new task in the default Google Tasks list.

    Args:
        title: Title of the task.
        notes: Optional description or notes for the task.
        due: Optional due date in RFC 3339 format (e.g., '2026-05-01T12:00:00Z').
    """
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = TasksClient(token)
    try:
        task = await client.create_task(title, notes, due)
        return {"status": "success", "task": task}
    except Exception as e:
        return _tool_error(f"Tasks create failed: {e}")


async def calendar_list(max_results: int = 10) -> dict[str, Any]:
    """List upcoming events from the user's primary Google Calendar."""
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = CalendarClient(token)
    try:
        events = await client.list_events(max_results=max_results)
        return {"status": "success", "events": events.get("items", [])}
    except Exception as e:
        return _tool_error(f"Calendar list failed: {e}")


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
    """
    token = await get_google_services_token_from_context()
    if not token:
        return _tool_error("Google services are not connected.")
    client = CalendarClient(token)
    try:
        event = await client.create_event(summary, start_time, end_time, description, location)
        return {"status": "success", "event": event}
    except Exception as e:
        return _tool_error(f"Calendar create failed: {e}")


def _slugify(value: str, *, fallback: str = "file") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


async def search_drive(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search the connected user's Google Drive files.

    Args:
        query: Search text to match against Drive file names or content.
        max_results: Maximum number of files to return.
    """
    client = await get_google_drive_client_from_context()
    if not client:
        return _tool_error("Google Drive is not connected for this user.")
    escaped_query = (query or "").replace("'", "\\'")
    q = f"fullText contains '{escaped_query}' and trashed = false"
    body = await client.list_files(
        params={
            "q": q,
            "pageSize": max(1, min(int(max_results or 10), 25)),
            "fields": "files(id,name,mimeType,webViewLink,modifiedTime,size)",
        }
    )
    return {"status": "success", "files": body.get("files", [])}


async def read_drive_file(file_id: str, max_chars: int = 12000) -> dict[str, Any]:
    """Read text content from a Google Drive file or exported Google Doc."""
    client = await get_google_drive_client_from_context()
    if not client:
        return _tool_error("Google Drive is not connected for this user.")
    meta = await client.get_file(file_id, params={"fields": "id,name,mimeType,webViewLink"})
    mime_type = str(meta.get("mimeType", ""))
    text = await client.read_text(file_id, mime_type)
    return {
        "status": "success",
        "file": meta,
        "content": text[: max(1000, min(int(max_chars or 12000), 50000))],
        "truncated": len(text) > max_chars,
    }


async def create_drive_doc(title: str, content: str) -> dict[str, Any]:
    """Create a Google Docs document in the connected user's Drive."""
    client = await get_google_drive_client_from_context()
    if not client:
        return _tool_error("Google Drive is not connected for this user.")
    created = await client.create_google_doc(title=title, content=content)
    return {"status": "success", "file": created}


async def upload_drive_file(filename: str, content_base64: str, mime_type: str = "application/octet-stream") -> dict[str, Any]:
    """Upload a base64-encoded file to the connected user's Google Drive."""
    client = await get_google_drive_client_from_context()
    if not client:
        return _tool_error("Google Drive is not connected for this user.")
    try:
        raw = await decode_base64_upload(content_base64)
    except Exception:
        return _tool_error("content_base64 must be valid base64.")
    uploaded = await client.upload_bytes(
        filename=filename,
        content=raw,
        mime_type=mime_type or "application/octet-stream",
    )
    return {"status": "success", "file": uploaded}


async def _github_token() -> str | None:
    repo = get_history_repository()
    owner_id = get_owner_id()
    if repo is None or not owner_id:
        return None
    connection = await repo.get_integration_connection(owner_id, "github")
    token = connection.private.get("token") if connection else None
    return token if isinstance(token, str) and token else None


async def _github_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    token = await _github_token()
    if not token:
        return _tool_error("GitHub is not connected for this user.")
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
            return _tool_error(
                f"GitHub API returned HTTP {response.status_code}.",
                detail=response.text[:500],
            )
        return {"status": "success", "data": response.json() if response.content else {}}


async def github_search_repos(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search GitHub repositories visible to the connected GitHub token."""
    result = await _github_request(
        "GET",
        "/search/repositories",
        params={"q": query, "per_page": max(1, min(int(max_results or 10), 25))},
    )
    if result.get("status") != "success":
        return result
    items = result["data"].get("items", [])
    return {
        "status": "success",
        "repositories": [
            {
                "full_name": item.get("full_name"),
                "description": item.get("description"),
                "html_url": item.get("html_url"),
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
            }
            for item in items
        ],
    }


async def github_read_file(owner: str, repo: str, path: str, ref: str = "main", max_chars: int = 20000) -> dict[str, Any]:
    """Read a file from a GitHub repository visible to the connected token."""
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}",
        params={"ref": ref},
    )
    if result.get("status") != "success":
        return result
    data = result["data"]
    encoded = data.get("content", "")
    try:
        content = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        return _tool_error("GitHub returned file content that could not be decoded.")
    limit = max(1000, min(int(max_chars or 20000), 50000))
    return {
        "status": "success",
        "file": {
            "name": data.get("name"),
            "path": data.get("path"),
            "sha": data.get("sha"),
            "html_url": data.get("html_url"),
        },
        "content": content[:limit],
        "truncated": len(content) > limit,
    }


async def github_list_issues(owner: str, repo: str, state: str = "open", max_results: int = 20) -> dict[str, Any]:
    """List GitHub issues for a repository visible to the connected token."""
    result = await _github_request(
        "GET",
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": max(1, min(int(max_results or 20), 50))},
    )
    if result.get("status") != "success":
        return result
    return {
        "status": "success",
        "issues": [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "html_url": item.get("html_url"),
                "user": (item.get("user") or {}).get("login"),
            }
            for item in result["data"]
            if "pull_request" not in item
        ],
    }


async def github_create_issue(owner: str, repo: str, title: str, body: str = "", labels: list[str] | None = None) -> dict[str, Any]:
    """Create a GitHub issue in a repository visible to the connected token."""
    result = await _github_request(
        "POST",
        f"/repos/{owner}/{repo}/issues",
        json={"title": title, "body": body, "labels": labels or []},
    )
    if result.get("status") != "success":
        return result
    data = result["data"]
    return {
        "status": "success",
        "issue": {
            "number": data.get("number"),
            "title": data.get("title"),
            "html_url": data.get("html_url"),
            "state": data.get("state"),
        },
    }


async def github_summarize_pr(owner: str, repo: str, pull_number: int) -> dict[str, Any]:
    """Fetch pull request metadata and changed files so the agent can summarize it."""
    pr = await _github_request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}")
    if pr.get("status") != "success":
        return pr
    files = await _github_request("GET", f"/repos/{owner}/{repo}/pulls/{pull_number}/files")
    if files.get("status") != "success":
        return files
    pr_data = pr["data"]
    file_data = files["data"]
    return {
        "status": "success",
        "pull_request": {
            "number": pr_data.get("number"),
            "title": pr_data.get("title"),
            "state": pr_data.get("state"),
            "html_url": pr_data.get("html_url"),
            "body": pr_data.get("body"),
        },
        "files": [
            {
                "filename": item.get("filename"),
                "status": item.get("status"),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
                "patch": item.get("patch", "")[:4000],
            }
            for item in file_data[:50]
        ],
    }
