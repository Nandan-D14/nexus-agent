# Proprietary and non-commercial use only.

"""Integration connection persistence (MCP, GitHub, Tavily, TinyFish, Thesys, Google)."""

from __future__ import annotations

import asyncio
from typing import Any

from firebase_admin import firestore
from nexus._firestore_base import FirestoreRepoBase
from nexus.history_models import StoredIntegrationConnection, utcnow


class IntegrationRepository(FirestoreRepoBase):
    async def list_integration_connections(self, uid: str) -> list[StoredIntegrationConnection]:
        return await asyncio.to_thread(self._list_integration_connections_sync, uid)

    async def list_enabled_integration_connections(self, uid: str) -> list[StoredIntegrationConnection]:
        return await asyncio.to_thread(self._list_enabled_integration_connections_sync, uid)

    async def get_integration_connection(
        self,
        uid: str,
        connection_id: str,
    ) -> StoredIntegrationConnection | None:
        return await asyncio.to_thread(self._get_integration_connection_sync, uid, connection_id)

    async def upsert_mcp_connection(
        self,
        uid: str,
        *,
        connection_id: str,
        name: str,
        url: str,
        bearer_token: str = "",
        enabled: bool = True,
        tools: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        status: str = "needs_setup",
        last_error: str | None = None,
        latency_ms: int | None = None,
    ) -> StoredIntegrationConnection:
        return await asyncio.to_thread(
            self._upsert_mcp_connection_sync,
            uid,
            connection_id,
            name,
            url,
            bearer_token,
            enabled,
            tools,
            resources,
            status,
            last_error,
            latency_ms,
        )

    async def upsert_github_connection(
        self,
        uid: str,
        *,
        token: str,
        enabled: bool = True,
        status: str = "connected",
        last_error: str | None = None,
    ) -> StoredIntegrationConnection:
        return await asyncio.to_thread(
            self._upsert_github_connection_sync,
            uid,
            token,
            enabled,
            status,
            last_error,
        )

    async def upsert_tavily_connection(
        self,
        uid: str,
        *,
        api_key: str,
        enabled: bool = True,
        status: str = "connected",
        last_error: str | None = None,
    ) -> StoredIntegrationConnection:
        return await asyncio.to_thread(
            self._upsert_tavily_connection_sync,
            uid,
            api_key,
            enabled,
            status,
            last_error,
        )

    async def upsert_tinyfish_connection(
        self,
        uid: str,
        *,
        api_key: str,
        enabled: bool = True,
        status: str = "connected",
        last_error: str | None = None,
    ) -> StoredIntegrationConnection:
        return await asyncio.to_thread(
            self._upsert_tinyfish_connection_sync,
            uid,
            api_key,
            enabled,
            status,
            last_error,
        )

    async def upsert_thesys_connection(
        self,
        uid: str,
        *,
        api_key: str,
        enabled: bool = True,
        status: str = "connected",
        last_error: str | None = None,
    ) -> StoredIntegrationConnection:
        return await asyncio.to_thread(
            self._upsert_thesys_connection_sync,
            uid,
            api_key,
            enabled,
            status,
            last_error,
        )

    async def upsert_google_connections(
        self,
        uid: str,
        *,
        enabled: bool = True,
        status: str = "connected",
        last_error: str | None = None,
    ) -> list[StoredIntegrationConnection]:
        return await asyncio.to_thread(
            self._upsert_google_connections_sync,
            uid,
            enabled,
            status,
            last_error,
        )

    async def update_integration_connection(
        self,
        uid: str,
        connection_id: str,
        *,
        enabled: bool | None = None,
        status: str | None = None,
        last_error: str | None = None,
    ) -> StoredIntegrationConnection | None:
        return await asyncio.to_thread(
            self._update_integration_connection_sync,
            uid,
            connection_id,
            enabled,
            status,
            last_error,
        )

    async def delete_integration_connection(self, uid: str, connection_id: str) -> bool:
        return await asyncio.to_thread(self._delete_integration_connection_sync, uid, connection_id)

    def _integration_public_ref(self, uid: str, connection_id: str):
        return (
            self._user_public_ref(uid)
            .collection("integrations")
            .document(connection_id)
        )

    def _integration_private_ref(self, uid: str, connection_id: str):
        return (
            self._user_private_ref(uid)
            .collection("integrations")
            .document(connection_id)
        )

    @staticmethod
    def _public_integration_payload(private_payload: dict[str, Any]) -> dict[str, Any]:
        tools = private_payload.get("tools") if isinstance(private_payload.get("tools"), list) else []
        resources = (
            private_payload.get("resources")
            if isinstance(private_payload.get("resources"), list)
            else []
        )
        return {
            "ownerId": private_payload.get("ownerId", ""),
            "connectorType": private_payload.get("connectorType", ""),
            "provider": private_payload.get("provider", ""),
            "name": private_payload.get("name", ""),
            "enabled": bool(private_payload.get("enabled")),
            "status": private_payload.get("status", "needs_setup"),
            "tools": tools,
            "resources": resources,
            "toolCount": len(tools),
            "resourceCount": len(resources),
            "lastCheckedAt": private_payload.get("lastCheckedAt"),
            "lastError": private_payload.get("lastError"),
            "createdAt": private_payload.get("createdAt"),
            "updatedAt": private_payload.get("updatedAt"),
        }

    def _sync_integration_summary_sync(self, uid: str) -> None:
        docs = self._user_public_ref(uid).collection("integrations").stream()
        summary = []
        for doc in docs:
            data = doc.to_dict() or {}
            summary.append(
                {
                    "connectionId": doc.id,
                    "provider": data.get("provider", ""),
                    "connectorType": data.get("connectorType", ""),
                    "name": data.get("name", doc.id),
                    "enabled": bool(data.get("enabled")),
                    "status": data.get("status", "needs_setup"),
                    "toolCount": int(data.get("toolCount", 0) or 0),
                    "lastError": data.get("lastError"),
                }
            )
        self._user_public_ref(uid).set(
            {
                "integrationSummary": summary,
                "updatedAt": utcnow(),
            },
            merge=True,
        )

    def _get_integration_connection_sync(
        self,
        uid: str,
        connection_id: str,
    ) -> StoredIntegrationConnection | None:
        public_doc = self._integration_public_ref(uid, connection_id).get()
        private_doc = self._integration_private_ref(uid, connection_id).get()
        if not public_doc.exists and not private_doc.exists:
            return None
        public_data = public_doc.to_dict() if public_doc.exists else {}
        private_data = private_doc.to_dict() if private_doc.exists else {}
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_data or {},
            private_data or {},
        )

    def _list_integration_connections_sync(self, uid: str) -> list[StoredIntegrationConnection]:
        docs = self._user_public_ref(uid).collection("integrations").stream()
        connections = []
        for doc in docs:
            private_doc = self._integration_private_ref(uid, doc.id).get()
            connections.append(
                self._build_stored_integration_connection(
                    uid,
                    doc.id,
                    doc.to_dict() or {},
                    private_doc.to_dict() if private_doc.exists else {},
                )
            )
        connections.sort(key=lambda item: item.updated_at, reverse=True)
        return connections

    def _list_enabled_integration_connections_sync(self, uid: str) -> list[StoredIntegrationConnection]:
        return [
            connection
            for connection in self._list_integration_connections_sync(uid)
            if connection.enabled and connection.status == "connected"
        ]

    def _upsert_mcp_connection_sync(
        self,
        uid: str,
        connection_id: str,
        name: str,
        url: str,
        bearer_token: str,
        enabled: bool,
        tools: list[dict[str, Any]] | None,
        resources: list[dict[str, Any]] | None,
        status: str,
        last_error: str | None,
        latency_ms: int | None,
    ) -> StoredIntegrationConnection:
        now = utcnow()
        existing = self._integration_private_ref(uid, connection_id).get()
        existing_data = existing.to_dict() if existing.exists else {}
        private_payload = {
            **existing_data,
            "ownerId": uid,
            "connectorType": "mcp_remote_http",
            "provider": "mcp",
            "name": name.strip()[:80] or "MCP Server",
            "url": url,
            "authType": "bearer" if bearer_token else existing_data.get("authType", "none"),
            "enabled": enabled,
            "tools": tools or [],
            "resources": resources or [],
            "status": status,
            "lastError": last_error,
            "lastCheckedAt": now,
            "updatedAt": now,
        }
        if bearer_token:
            private_payload["bearerToken"] = bearer_token
        if latency_ms is not None:
            private_payload["latencyMs"] = latency_ms
        if not existing_data.get("createdAt"):
            private_payload["createdAt"] = now

        public_payload = self._public_integration_payload(private_payload)
        batch = self._db.batch()
        batch.set(self._integration_private_ref(uid, connection_id), private_payload, merge=True)
        batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_payload,
            private_payload,
        )

    def _upsert_github_connection_sync(
        self,
        uid: str,
        token: str,
        enabled: bool,
        status: str,
        last_error: str | None,
    ) -> StoredIntegrationConnection:
        now = utcnow()
        connection_id = "github"
        private_payload = {
            "ownerId": uid,
            "connectorType": "native",
            "provider": "github",
            "name": "GitHub",
            "token": token,
            "enabled": enabled,
            "tools": [
                {"name": "github_search_repos", "description": "Search GitHub repositories."},
                {"name": "github_read_file", "description": "Read a repository file."},
                {"name": "github_list_issues", "description": "List repository issues."},
                {"name": "github_create_issue", "description": "Create a repository issue."},
                {"name": "github_summarize_pr", "description": "Fetch PR metadata and changed files."},
            ],
            "resources": [],
            "status": status,
            "lastError": last_error,
            "lastCheckedAt": now,
            "updatedAt": now,
        }
        existing = self._integration_private_ref(uid, connection_id).get()
        existing_data = existing.to_dict() if existing.exists else {}
        private_payload["createdAt"] = existing_data.get("createdAt") or now
        public_payload = self._public_integration_payload(private_payload)
        batch = self._db.batch()
        batch.set(self._integration_private_ref(uid, connection_id), private_payload, merge=True)
        batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_payload,
            private_payload,
        )

    def _upsert_tavily_connection_sync(
        self,
        uid: str,
        api_key: str,
        enabled: bool,
        status: str,
        last_error: str | None,
    ) -> StoredIntegrationConnection:
        now = utcnow()
        connection_id = "tavily"
        private_payload = {
            "ownerId": uid,
            "connectorType": "native",
            "provider": "tavily",
            "name": "Tavily",
            "apiKey": api_key,
            "enabled": enabled,
            "tools": [
                {"name": "tavily_search", "description": "Search the web using Tavily AI search engine."},
            ],
            "resources": [],
            "status": status,
            "lastError": last_error,
            "lastCheckedAt": now,
            "updatedAt": now,
        }
        existing = self._integration_private_ref(uid, connection_id).get()
        existing_data = existing.to_dict() if existing.exists else {}
        private_payload["createdAt"] = existing_data.get("createdAt") or now
        public_payload = self._public_integration_payload(private_payload)
        batch = self._db.batch()
        batch.set(self._integration_private_ref(uid, connection_id), private_payload, merge=True)
        batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_payload,
            private_payload,
        )

    def _upsert_tinyfish_connection_sync(
        self,
        uid: str,
        api_key: str,
        enabled: bool,
        status: str,
        last_error: str | None,
    ) -> StoredIntegrationConnection:
        now = utcnow()
        connection_id = "tinyfish"
        private_payload = {
            "ownerId": uid,
            "connectorType": "native",
            "provider": "tinyfish",
            "name": "Tinyfish",
            "apiKey": api_key,
            "enabled": enabled,
            "tools": [
                {"name": "tinyfish_web_agent", "description": "Use TinyFish to automate browser tasks on a website using natural language goals."},
            ],
            "resources": [],
            "status": status,
            "lastError": last_error,
            "lastCheckedAt": now,
            "updatedAt": now,
        }
        existing = self._integration_private_ref(uid, connection_id).get()
        existing_data = existing.to_dict() if existing.exists else {}
        private_payload["createdAt"] = existing_data.get("createdAt") or now
        public_payload = self._public_integration_payload(private_payload)
        batch = self._db.batch()
        batch.set(self._integration_private_ref(uid, connection_id), private_payload, merge=True)
        batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_payload,
            private_payload,
        )

    def _upsert_thesys_connection_sync(
        self,
        uid: str,
        api_key: str,
        enabled: bool,
        status: str,
        last_error: str | None,
    ) -> StoredIntegrationConnection:
        now = utcnow()
        connection_id = "thesys"
        private_payload = {
            "ownerId": uid,
            "connectorType": "native",
            "provider": "thesys",
            "name": "Thesys",
            "apiKey": api_key,
            "enabled": enabled,
            "tools": [
                {"name": "render_ui", "description": "Generate interactive UI components (charts, tables, forms, dashboards) from data."},
            ],
            "resources": [],
            "status": status,
            "lastError": last_error,
            "lastCheckedAt": now,
            "updatedAt": now,
        }
        existing = self._integration_private_ref(uid, connection_id).get()
        existing_data = existing.to_dict() if existing.exists else {}
        private_payload["createdAt"] = existing_data.get("createdAt") or now
        public_payload = self._public_integration_payload(private_payload)
        batch = self._db.batch()
        batch.set(self._integration_private_ref(uid, connection_id), private_payload, merge=True)
        batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_payload,
            private_payload,
        )

    def _upsert_google_connections_sync(
        self,
        uid: str,
        enabled: bool,
        status: str,
        last_error: str | None,
    ) -> list[StoredIntegrationConnection]:
        now = utcnow()
        specs = {
            "google_drive": {
                "provider": "google_drive",
                "name": "Google Drive",
                "tools": [
                    {"name": "search_drive", "description": "Search Google Drive files."},
                    {"name": "read_drive_file", "description": "Read a Google Drive file."},
                    {"name": "create_drive_doc", "description": "Create a Google Docs document."},
                    {"name": "upload_drive_file", "description": "Upload a file to Google Drive."},
                ],
            },
            "gmail": {
                "provider": "gmail",
                "name": "Gmail",
                "tools": [
                    {"name": "gmail_search", "description": "Search Gmail messages."},
                    {"name": "gmail_read", "description": "Read a Gmail message."},
                    {"name": "gmail_send", "description": "Send a Gmail message."},
                ],
            },
            "google_calendar": {
                "provider": "google_calendar",
                "name": "Google Calendar",
                "tools": [
                    {"name": "calendar_list", "description": "List Google Calendar events."},
                    {"name": "calendar_create", "description": "Create a Google Calendar event."},
                ],
            },
            "google_tasks": {
                "provider": "google_tasks",
                "name": "Google Tasks",
                "tools": [
                    {"name": "tasks_list", "description": "List Google Tasks."},
                    {"name": "tasks_create", "description": "Create a Google Task."},
                ],
            },
        }
        batch = self._db.batch()
        private_by_id: dict[str, dict[str, Any]] = {}
        public_by_id: dict[str, dict[str, Any]] = {}
        for connection_id, spec in specs.items():
            existing = self._integration_private_ref(uid, connection_id).get()
            existing_data = existing.to_dict() if existing.exists else {}
            private_payload = {
                "ownerId": uid,
                "connectorType": "native",
                "provider": spec["provider"],
                "name": spec["name"],
                "enabled": enabled,
                "tools": spec["tools"],
                "resources": [],
                "status": status,
                "lastError": last_error,
                "lastCheckedAt": now,
                "createdAt": existing_data.get("createdAt") or now,
                "updatedAt": now,
            }
            public_payload = self._public_integration_payload(private_payload)
            private_by_id[connection_id] = private_payload
            public_by_id[connection_id] = public_payload
            batch.set(self._integration_private_ref(uid, connection_id), private_payload, merge=True)
            batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        
        return [
            self._build_stored_integration_connection(
                uid,
                cid,
                public_by_id[cid],
                private_by_id[cid],
            )
            for cid in specs.keys()
        ]

    def _update_integration_connection_sync(
        self,
        uid: str,
        connection_id: str,
        enabled: bool | None,
        status: str | None,
        last_error: str | None,
    ) -> StoredIntegrationConnection | None:
        existing = self._get_integration_connection_sync(uid, connection_id)
        if not existing:
            return None
        now = utcnow()
        updates: dict[str, Any] = {"updatedAt": now}
        if enabled is not None:
            updates["enabled"] = enabled
        if status is not None:
            updates["status"] = status
        if last_error is not None:
            updates["lastError"] = last_error
        private_payload = {**existing.private, **updates}
        public_payload = self._public_integration_payload(private_payload)
        batch = self._db.batch()
        batch.set(self._integration_private_ref(uid, connection_id), updates, merge=True)
        batch.set(self._integration_public_ref(uid, connection_id), public_payload, merge=True)
        batch.commit()
        self._sync_integration_summary_sync(uid)
        return self._build_stored_integration_connection(
            uid,
            connection_id,
            public_payload,
            private_payload,
        )

    def _delete_integration_connection_sync(self, uid: str, connection_id: str) -> bool:
        existing = self._get_integration_connection_sync(uid, connection_id)
        if not existing:
            return False
        self._integration_private_ref(uid, connection_id).delete()
        self._integration_public_ref(uid, connection_id).delete()
        self._sync_integration_summary_sync(uid)
        return True
