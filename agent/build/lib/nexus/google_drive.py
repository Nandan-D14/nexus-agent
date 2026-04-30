"""Shared Google Drive helpers for native tools and session uploads."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from nexus.config import settings

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DOC_MIME_TYPE = "application/vnd.google-apps.document"


def _escape_drive_query(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveClient:
    def __init__(self, access_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def list_files(self, *, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, headers=self._headers) as client:
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params=params,
            )
            response.raise_for_status()
        return response.json()

    async def get_file(self, file_id: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, headers=self._headers) as client:
            response = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params=params,
            )
            response.raise_for_status()
        return response.json()

    async def read_text(self, file_id: str, mime_type: str) -> str:
        async with httpx.AsyncClient(timeout=40.0, headers=self._headers) as client:
            if mime_type.startswith("application/vnd.google-apps."):
                response = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                    params={"mimeType": "text/plain"},
                )
            else:
                response = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    params={"alt": "media"},
                )
            response.raise_for_status()
        return response.text

    async def ensure_folder_path(self, parts: list[str]) -> dict[str, Any]:
        parent_id = "root"
        created: list[dict[str, Any]] = []
        for raw_part in parts:
            name = (raw_part or "").strip()
            if not name:
                continue
            folder = await self._find_folder(name, parent_id)
            if folder is None:
                folder = await self._create_folder(name, parent_id)
            created.append(folder)
            parent_id = str(folder.get("id") or parent_id)
        return {
            "folder_id": parent_id,
            "folders": created,
            "path": "/".join(part.strip() for part in parts if part.strip()),
        }

    async def create_google_doc(
        self,
        *,
        title: str,
        content: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "name": title.strip()[:120] or "CoComputer Report",
            "mimeType": DOC_MIME_TYPE,
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        return await self._multipart_upload(
            metadata=metadata,
            body=(content or "").encode("utf-8"),
            content_type="text/plain; charset=UTF-8",
            fields="id,name,mimeType,webViewLink,parents",
        )

    async def upload_bytes(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {"name": filename.strip()[:160] or "upload.bin"}
        if parent_id:
            metadata["parents"] = [parent_id]
        return await self._multipart_upload(
            metadata=metadata,
            body=content,
            content_type=mime_type or "application/octet-stream",
            fields="id,name,mimeType,webViewLink,parents",
        )

    async def _find_folder(self, name: str, parent_id: str) -> dict[str, Any] | None:
        query = (
            f"name = '{_escape_drive_query(name)}' and "
            f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false and "
            f"'{parent_id}' in parents"
        )
        body = await self.list_files(
            params={
                "q": query,
                "pageSize": 1,
                "fields": "files(id,name,mimeType,webViewLink,parents)",
            }
        )
        files = body.get("files")
        if isinstance(files, list) and files:
            first = files[0]
            return first if isinstance(first, dict) else None
        return None

    async def _create_folder(self, name: str, parent_id: str) -> dict[str, Any]:
        return await self._multipart_upload(
            metadata={
                "name": name.strip()[:160] or "Folder",
                "mimeType": FOLDER_MIME_TYPE,
                "parents": [parent_id],
            },
            body=b"",
            content_type="application/octet-stream",
            fields="id,name,mimeType,webViewLink,parents",
        )

    async def _multipart_upload(
        self,
        *,
        metadata: dict[str, Any],
        body: bytes,
        content_type: str,
        fields: str,
    ) -> dict[str, Any]:
        boundary = "cocomputer_drive_boundary"
        head = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        async with httpx.AsyncClient(
            timeout=60.0,
            headers={
                **self._headers,
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
        ) as client:
            response = await client.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "multipart", "fields": fields},
                content=head + body + tail,
            )
            response.raise_for_status()
        return response.json()


async def get_google_drive_access_token_for_user(
    repo: Any,
    user_id: str,
) -> str | None:
    if repo is None or not user_id:
        return None
    user_settings = await repo.get_user_settings(user_id)
    refresh_token = (user_settings or {}).get("googleDriveRefreshToken")
    if not refresh_token:
        return None
    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        return None
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
    token = response.json().get("access_token")
    return token if isinstance(token, str) and token else None


async def get_google_drive_client_for_user(repo: Any, user_id: str) -> GoogleDriveClient | None:
    token = await get_google_drive_access_token_for_user(repo, user_id)
    if not token:
        return None
    return GoogleDriveClient(token)


async def get_google_drive_client_from_context() -> GoogleDriveClient | None:
    from nexus.tools._context import get_history_repository, get_owner_id

    return await get_google_drive_client_for_user(get_history_repository(), get_owner_id())


async def decode_base64_upload(content_base64: str) -> bytes:
    return base64.b64decode(content_base64)
