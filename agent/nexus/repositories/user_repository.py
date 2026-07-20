# Proprietary and non-commercial use only.

"""User account, settings, quota, and starter-plan persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists

from nexus._firestore_base import FirestoreRepoBase
from nexus.auth import AuthenticatedUser
from nexus.billing import build_quota_payload
from nexus.config import settings
from nexus.history_models import utcnow


class UserRepository(FirestoreRepoBase):
    async def upsert_user(self, user: AuthenticatedUser) -> None:
        await asyncio.to_thread(self._upsert_user_sync, user)

    async def get_user_settings(self, uid: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_user_settings_sync, uid)

    async def update_user_settings(self, uid: str, updates: dict[str, Any]) -> None:
        return await asyncio.to_thread(self._update_user_settings_sync, uid, updates)

    async def get_user_quota(self, uid: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_user_quota_sync, uid)

    async def increment_user_token_usage(self, uid: str, tokens: int) -> dict[str, Any]:
        """Atomically increment user-level token usage. Returns updated quota."""
        return await asyncio.to_thread(self._increment_user_token_usage_sync, uid, tokens)

    async def increment_user_credit_usage(self, uid: str, credits: int) -> dict[str, Any]:
        """Atomically increment user-level credit usage. Returns updated quota."""
        return await asyncio.to_thread(self._increment_user_credit_usage_sync, uid, credits)

    @staticmethod
    def _starter_plan_defaults(now: datetime) -> dict[str, Any]:
        return {
            "planId": settings.default_plan_id,
            "planName": settings.default_plan_name,
            "planPriceUsd": settings.default_plan_price_usd,
            "planStatus": "active",
            "billingMode": "internal_entitlement",
            "creditLimit": settings.default_credit_limit,
            "creditUsage": 0,
            "creditUnitUsd": settings.default_credit_unit_usd,
            "creditResetVersion": settings.default_credit_reset_version,
            "creditResetAt": now,
            "updatedAt": now,
        }

    def _build_starter_plan_updates(self, data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        defaults = self._starter_plan_defaults(now)
        if data.get("creditResetVersion") != settings.default_credit_reset_version:
            forced_reset = dict(defaults)
            if "migratedFromFreeTierAt" not in data:
                forced_reset["migratedFromFreeTierAt"] = now
            return forced_reset

        updates: dict[str, Any] = {}
        for key, value in defaults.items():
            current = data.get(key)
            if isinstance(value, str):
                if not isinstance(current, str) or not current.strip():
                    updates[key] = value
            elif current is None:
                updates[key] = value
        if updates and "migratedFromFreeTierAt" not in data:
            updates["migratedFromFreeTierAt"] = now
        return updates

    def _upsert_user_sync(self, user: AuthenticatedUser) -> None:
        now = utcnow()
        ref = self._user_public_ref(user.uid)
        base_payload: dict[str, Any] = {
            "uid": user.uid,
            "email": user.email,
            "displayName": user.display_name,
            "photoURL": user.photo_url,
            "lastLoginAt": now,
        }
        try:
            # Atomic create — sets createdAt and token quota only when the document is new.
            ref.create({
                **base_payload,
                "createdAt": now,
                "tokenUsage": 0,
                "tokenLimit": settings.default_token_limit,
                **self._starter_plan_defaults(now),
            })
        except AlreadyExists:
            # Document already exists; update mutable fields only.
            existing = ref.get()
            data = existing.to_dict() or {}
            ref.set(
                {
                    **base_payload,
                    **self._build_starter_plan_updates(data, now=now),
                },
                merge=True,
            )

    def _get_user_settings_sync(self, uid: str) -> dict[str, Any]:
        public_ref = self._user_public_ref(uid)
        private_ref = self._user_private_ref(uid)

        public_doc = public_ref.get()
        private_doc = private_ref.get()

        public_data = public_doc.to_dict() or {}
        private_data = private_doc.to_dict() or {}

        private_updates: dict[str, Any] = {}
        delete_byok = False
        delete_google_drive_refresh_token = False
        delete_google_drive_tokens = False

        legacy_byok = public_data.get("byok")
        if isinstance(legacy_byok, dict):
            if not isinstance(private_data.get("byok"), dict):
                private_updates["byok"] = legacy_byok
            delete_byok = True

        if "googleDriveRefreshToken" in public_data:
            if "googleDriveRefreshToken" not in private_data:
                private_updates["googleDriveRefreshToken"] = public_data.get("googleDriveRefreshToken")
            delete_google_drive_refresh_token = True

        if "googleDriveTokens" in public_data:
            delete_google_drive_tokens = True

        if private_updates:
            private_updates["updatedAt"] = utcnow()
            self._apply_document_updates_sync(private_ref, private_updates)
            private_data = {**private_data, **private_updates}

        if delete_byok or delete_google_drive_refresh_token or delete_google_drive_tokens:
            self._cleanup_public_user_sensitive_fields_sync(
                uid,
                delete_byok=delete_byok,
                delete_google_drive_refresh_token=delete_google_drive_refresh_token,
                delete_google_drive_tokens=delete_google_drive_tokens,
            )
            public_data.pop("byok", None)
            public_data.pop("googleDriveRefreshToken", None)
            public_data.pop("googleDriveTokens", None)

        merged = dict(public_data)
        merged.update(private_data)
        return merged

    def _update_user_settings_sync(self, uid: str, updates: dict[str, Any]) -> None:
        before_settings = self._get_user_settings_sync(uid)
        
        public_updates, private_updates = self._partition_user_settings_updates(updates)
        now = utcnow()

        if public_updates:
            public_updates.setdefault("updatedAt", now)
            self._apply_document_updates_sync(self._user_public_ref(uid), public_updates)

        if private_updates:
            private_updates.setdefault("updatedAt", now)
            self._apply_document_updates_sync(self._user_private_ref(uid), private_updates)
            self._cleanup_public_user_sensitive_fields_sync(
                uid,
                delete_byok=any(key == "byok" or key.startswith("byok.") for key in private_updates),
                delete_google_drive_refresh_token=any(
                    key == "googleDriveRefreshToken" or key.startswith("googleDriveRefreshToken.")
                    for key in private_updates
                ),
                delete_google_drive_tokens="googleDriveRefreshToken" in private_updates,
            )

        after_settings = self._get_user_settings_sync(uid)
        self._create_audit_log_sync(
            actor_uid=uid,
            action="settings_change",
            target_uid=uid,
            before=before_settings,
            after=after_settings
        )

    def _get_user_quota_sync(self, uid: str) -> dict[str, Any]:
        ref = self._db.collection("users").document(uid)
        doc = ref.get()
        if not doc.exists:
            return build_quota_payload(None)
        data = doc.to_dict() or {}
        updates = self._build_starter_plan_updates(data, now=utcnow())
        if updates:
            ref.set(updates, merge=True)
            data = {**data, **updates}
        return build_quota_payload(data)

    def _increment_user_token_usage_sync(self, uid: str, tokens: int) -> dict[str, Any]:
        if tokens <= 0:
            return self._get_user_quota_sync(uid)

        ref = self._db.collection("users").document(uid)
        ref.update({"tokenUsage": firestore.Increment(tokens)})
        return self._get_user_quota_sync(uid)

    def _increment_user_credit_usage_sync(self, uid: str, credits: int) -> dict[str, Any]:
        if credits <= 0:
            return self._get_user_quota_sync(uid)

        ref = self._db.collection("users").document(uid)
        doc = ref.get()
        data = doc.to_dict() if doc.exists else {}
        updates = self._build_starter_plan_updates(data or {}, now=utcnow())
        if updates:
            ref.set(updates, merge=True)
        ref.update({"creditUsage": firestore.Increment(int(credits))})
        return self._get_user_quota_sync(uid)
