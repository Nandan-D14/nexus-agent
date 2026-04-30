"""Shared Google service clients for Gmail, Tasks, and Calendar."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from nexus.config import settings
from nexus.google_drive import get_google_drive_access_token_for_user


class GoogleServiceClient:
    def __init__(self, access_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, headers=self._headers) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=json_body,
            )
            response.raise_for_status()
            return response.json() if response.content else {}


class GmailClient(GoogleServiceClient):
    async def list_messages(self, query: str = "", max_results: int = 10) -> dict[str, Any]:
        params = {"q": query, "maxResults": max_results}
        return await self._request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", params=params)

    async def get_message(self, message_id: str) -> dict[str, Any]:
        return await self._request("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}")

    async def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        import base64
        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return await self._request(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json_body={"raw": raw},
        )


class TasksClient(GoogleServiceClient):
    async def list_task_lists(self) -> dict[str, Any]:
        return await self._request("GET", "https://tasks.googleapis.com/tasks/v1/users/@me/lists")

    async def list_tasks(self, list_id: str = "@default") -> dict[str, Any]:
        return await self._request("GET", f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks")

    async def create_task(self, title: str, notes: str = "", due: str | None = None, list_id: str = "@default") -> dict[str, Any]:
        body = {"title": title, "notes": notes}
        if due:
            body["due"] = due
        return await self._request("POST", f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks", json_body=body)


class CalendarClient(GoogleServiceClient):
    async def list_events(self, calendar_id: str = "primary", max_results: int = 10) -> dict[str, Any]:
        params = {"maxResults": max_results, "timeMin": datetime.now(timezone.utc).isoformat()}
        return await self._request("GET", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events", params=params)

    async def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        return await self._request("POST", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events", json_body=body)


async def get_google_services_token_from_context() -> str | None:
    from nexus.tools._context import get_history_repository, get_owner_id
    return await get_google_drive_access_token_for_user(get_history_repository(), get_owner_id())
