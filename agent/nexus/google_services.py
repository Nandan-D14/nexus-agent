# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared Google service clients for Gmail, Tasks, and Calendar."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from nexus.google_drive import get_google_drive_access_token_for_user


class GoogleApiError(Exception):
    def __init__(self, message: str, *, error_code: str = "", status_code: int = 0) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


def explain_google_http_error(response: httpx.Response, *, service: str = "Google") -> GoogleApiError:
    text = (response.text or "")[:800]
    compact = "".join(text.lower().split())
    if response.status_code in {401, 403} and (
        "insufficient" in compact
        or "accesstokenscopeinsufficient" in compact
        or "insufficientauthentication" in compact
    ):
        return GoogleApiError(
            f"{service} is missing permission. Disconnect Google in Connectors and reconnect so the required Google scopes are granted.",
            error_code="AUTH_REQUIRED",
            status_code=response.status_code,
        )
    if response.status_code == 403 and (
        "accessnotconfigured" in compact
        or "hasnotbeenused" in compact
        or "isdisabled" in compact
        or "calendarapi" in compact
    ):
        return GoogleApiError(
            "Google Calendar API is not enabled on this OAuth project's Google Cloud account. Enable Calendar API, then retry.",
            error_code="AUTH_REQUIRED",
            status_code=403,
        )
    return GoogleApiError(
        f"{service} request failed (HTTP {response.status_code}): {text[:240]}",
        error_code=f"HTTP_{response.status_code}",
        status_code=response.status_code,
    )


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
            if response.status_code >= 400:
                if "calendar" in url:
                    service = "Google Calendar"
                elif "gmail" in url:
                    service = "Gmail"
                elif "tasks" in url:
                    service = "Google Tasks"
                else:
                    service = "Google"
                raise explain_google_http_error(response, service=service)
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


def slim_calendar_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields the Workspace dashboard and agent summaries need."""
    start = event.get("start") if isinstance(event.get("start"), dict) else {}
    end = event.get("end") if isinstance(event.get("end"), dict) else {}
    return {
        "id": str(event.get("id") or ""),
        "summary": str(event.get("summary") or ""),
        "start": str(start.get("dateTime") or start.get("date") or ""),
        "end": str(end.get("dateTime") or end.get("date") or ""),
        "htmlLink": str(event.get("htmlLink") or ""),
        "status": str(event.get("status") or ""),
    }


class CalendarClient(GoogleServiceClient):
    async def list_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 50,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min or datetime.now(timezone.utc).isoformat(),
        }
        if time_max:
            params["timeMax"] = time_max
        return await self._request("GET", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events", params=params)

    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        return await self._request("GET", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}")

    async def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        calendar_id: str = "primary",
        time_zone: str = "UTC",
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        zone = (time_zone or "UTC").strip() or "UTC"
        body: dict[str, Any] = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time, "timeZone": zone},
            "end": {"dateTime": end_time, "timeZone": zone},
        }
        emails = [
            email.strip()
            for email in (attendees or [])
            if isinstance(email, str) and email.strip()
        ]
        if emails:
            body["attendees"] = [{"email": email} for email in emails]
        return await self._request("POST", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events", json_body=body)

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        description: str | None = None,
        location: str | None = None,
        calendar_id: str = "primary",
        time_zone: str = "UTC",
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        zone = (time_zone or "UTC").strip() or "UTC"
        body: dict[str, Any] = {}
        if summary is not None:
            body["summary"] = summary
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        if start_time is not None:
            body["start"] = {"dateTime": start_time, "timeZone": zone}
        if end_time is not None:
            body["end"] = {"dateTime": end_time, "timeZone": zone}
        if attendees is not None:
            emails = [email.strip() for email in attendees if isinstance(email, str) and email.strip()]
            body["attendees"] = [{"email": email} for email in emails]
        return await self._request("PATCH", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}", json_body=body)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        return await self._request("DELETE", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}")


async def get_google_services_token_from_context() -> str | None:
    from nexus.tools._context import get_history_repository, get_owner_id
    return await get_google_drive_access_token_for_user(get_history_repository(), get_owner_id())
