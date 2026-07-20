# Proprietary and non-commercial use only.

"""Beta access application and access-code persistence."""

from __future__ import annotations

import asyncio
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from nexus._firestore_base import FirestoreRepoBase
from nexus.beta_access import normalize_beta_profile
from nexus.history_models import utcnow


class BetaRepository(FirestoreRepoBase):
    async def get_beta_application(self, uid: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_beta_application_sync, uid)

    async def upsert_beta_application(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_beta_application_sync, uid, payload)

    async def set_beta_profile(self, uid: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._set_beta_profile_sync, uid, payload)

    async def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._find_user_by_email_sync, email)

    async def issue_beta_access_code(
        self,
        *,
        uid: str,
        admin_email: str,
        code_hash: str,
        code_preview: str,
    ) -> None:
        await asyncio.to_thread(
            self._issue_beta_access_code_sync,
            uid,
            admin_email,
            code_hash,
            code_preview,
        )

    async def reject_beta_application(
        self,
        *,
        uid: str,
        admin_email: str,
        reason: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._reject_beta_application_sync, uid, admin_email, reason)

    async def revoke_beta_access(
        self,
        *,
        uid: str,
        admin_email: str,
        reason: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._revoke_beta_access_sync, uid, admin_email, reason)

    async def redeem_beta_access_code(self, uid: str, code_hash: str) -> None:
        await asyncio.to_thread(self._redeem_beta_access_code_sync, uid, code_hash)

    def _get_beta_application_sync(self, uid: str) -> dict[str, Any] | None:
        doc = self._db.collection("betaApplications").document(uid).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        data["id"] = doc.id
        return data

    def _upsert_beta_application_sync(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        ref = self._db.collection("betaApplications").document(uid)
        existing = ref.get()
        current = existing.to_dict() if existing.exists else {}
        next_payload = {
            **current,
            **payload,
            "userId": uid,
            "updatedAt": now,
        }
        if not current.get("submittedAt"):
            next_payload["submittedAt"] = now
        ref.set(next_payload, merge=True)
        next_payload["id"] = uid
        return next_payload

    def _set_beta_profile_sync(self, uid: str, payload: dict[str, Any]) -> None:
        self._db.collection("users").document(uid).set({"betaProfile": payload}, merge=True)

    def _find_user_by_email_sync(self, email: str) -> dict[str, Any] | None:
        query = (
            self._db.collection("users")
            .where(filter=FieldFilter("email", "==", email.strip()))
            .limit(1)
        )
        for doc in query.stream():
            data = doc.to_dict() or {}
            data["uid"] = doc.id
            return data
        return None

    def _issue_beta_access_code_sync(
        self,
        uid: str,
        admin_email: str,
        code_hash: str,
        code_preview: str,
    ) -> None:
        now = utcnow()
        user_ref = self._db.collection("users").document(uid)
        application_ref = self._db.collection("betaApplications").document(uid)
        code_ref = self._db.collection("betaAccessCodes").document(code_hash)
        batch = self._db.batch()

        existing_codes = (
            self._db.collection("betaAccessCodes")
            .where(filter=FieldFilter("assignedUserId", "==", uid))
            .stream()
        )
        for doc in existing_codes:
            data = doc.to_dict() or {}
            if data.get("status") != "available":
                continue
            batch.set(
                doc.reference,
                {
                    "status": "revoked",
                    "revokedAt": now,
                    "revokedBy": admin_email,
                    "revokeReason": "Replaced by a newer beta access code.",
                },
                merge=True,
            )

        user_snapshot = user_ref.get()
        user_data = user_snapshot.to_dict() if user_snapshot.exists else {}
        current_profile = normalize_beta_profile(user_data)
        batch.set(
            user_ref,
            {
                "betaProfile": {
                    **current_profile,
                    "status": "approved",
                    "applicationId": uid,
                    "applicationSubmittedAt": current_profile.get("applicationSubmittedAt")
                    or now,
                    "applicationUpdatedAt": now,
                    "approvedAt": now,
                    "rejectedAt": None,
                    "revokedAt": None,
                    "redeemedAt": None,
                    "accessCodeRedeemed": False,
                    "accessCodeId": None,
                    "accessCodePreview": None,
                    "lastDecisionBy": admin_email,
                    "rejectionReason": None,
                    "revokedReason": None,
                }
            },
            merge=True,
        )
        batch.set(
            application_ref,
            {
                "status": "approved",
                "reviewedAt": now,
                "approvedAt": now,
                "rejectedAt": None,
                "revokedAt": None,
                "reviewedBy": admin_email,
                "accessCodeRedeemedAt": None,
                "updatedAt": now,
            },
            merge=True,
        )
        batch.set(
            code_ref,
            {
                "assignedUserId": uid,
                "status": "available",
                "createdAt": now,
                "createdBy": admin_email,
                "preview": code_preview,
                "redeemedAt": None,
                "redeemedBy": None,
                "revokedAt": None,
                "revokedBy": None,
                "revokeReason": None,
            },
            merge=True,
        )
        batch.commit()

        after_user_data = user_ref.get().to_dict() or {}
        self._create_audit_log_sync(
            actor_uid=admin_email,
            action="beta_approve",
            target_uid=uid,
            before={"betaProfile": current_profile},
            after={"betaProfile": after_user_data.get("betaProfile")}
        )

    def _reject_beta_application_sync(self, uid: str, admin_email: str, reason: str | None = None) -> None:
        now = utcnow()
        user_ref = self._db.collection("users").document(uid)
        user_snapshot = user_ref.get()
        user_data = user_snapshot.to_dict() if user_snapshot.exists else {}
        current_profile = normalize_beta_profile(user_data)
        batch = self._db.batch()
        batch.set(
            user_ref,
            {
                "betaProfile": {
                    **current_profile,
                    "status": "rejected",
                    "applicationId": uid,
                    "applicationSubmittedAt": current_profile.get("applicationSubmittedAt"),
                    "applicationUpdatedAt": now,
                    "approvedAt": None,
                    "rejectedAt": now,
                    "revokedAt": None,
                    "redeemedAt": None,
                    "accessCodeRedeemed": False,
                    "accessCodeId": None,
                    "accessCodePreview": None,
                    "lastDecisionBy": admin_email,
                    "rejectionReason": reason[:500] if reason else None,
                    "revokedReason": None,
                }
            },
            merge=True,
        )
        batch.set(
            self._db.collection("betaApplications").document(uid),
            {
                "status": "rejected",
                "reviewedAt": now,
                "rejectedAt": now,
                "reviewedBy": admin_email,
                "rejectionReason": reason[:500] if reason else None,
                "updatedAt": now,
            },
            merge=True,
        )
        batch.commit()

        after_user_data = user_ref.get().to_dict() or {}
        self._create_audit_log_sync(
            actor_uid=admin_email,
            action="beta_reject",
            target_uid=uid,
            before={"betaProfile": current_profile},
            after={"betaProfile": after_user_data.get("betaProfile")}
        )

    def _revoke_beta_access_sync(self, uid: str, admin_email: str, reason: str | None = None) -> None:
        now = utcnow()
        user_ref = self._db.collection("users").document(uid)
        user_snapshot = user_ref.get()
        user_data = user_snapshot.to_dict() if user_snapshot.exists else {}
        current_profile = normalize_beta_profile(user_data)
        batch = self._db.batch()
        batch.set(
            user_ref,
            {
                "betaProfile": {
                    **current_profile,
                    "status": "revoked",
                    "applicationUpdatedAt": now,
                    "revokedAt": now,
                    "accessCodeRedeemed": False,
                    "lastDecisionBy": admin_email,
                    "revokedReason": reason[:500] if reason else None,
                }
            },
            merge=True,
        )
        batch.set(
            self._db.collection("betaApplications").document(uid),
            {
                "status": "revoked",
                "reviewedAt": now,
                "revokedAt": now,
                "reviewedBy": admin_email,
                "revokeReason": reason[:500] if reason else None,
                "updatedAt": now,
            },
            merge=True,
        )

        codes = (
            self._db.collection("betaAccessCodes")
            .where(filter=FieldFilter("assignedUserId", "==", uid))
            .stream()
        )
        for doc in codes:
            batch.set(
                doc.reference,
                {
                    "status": "revoked",
                    "revokedAt": now,
                    "revokedBy": admin_email,
                    "revokeReason": reason[:500] if reason else "Beta access revoked.",
                },
                merge=True,
            )
        batch.commit()

        after_user_data = user_ref.get().to_dict() or {}
        self._create_audit_log_sync(
            actor_uid=admin_email,
            action="beta_revoke",
            target_uid=uid,
            before={"betaProfile": current_profile},
            after={"betaProfile": after_user_data.get("betaProfile")}
        )

    def _redeem_beta_access_code_sync(self, uid: str, code_hash: str) -> None:
        transaction = self._db.transaction()
        user_ref = self._db.collection("users").document(uid)
        application_ref = self._db.collection("betaApplications").document(uid)
        code_ref = self._db.collection("betaAccessCodes").document(code_hash)

        @firestore.transactional
        def _redeem(txn):
            now = utcnow()
            user_doc = user_ref.get(transaction=txn)
            user_data = user_doc.to_dict() if user_doc.exists else {}
            profile = normalize_beta_profile(user_data)
            code_doc = code_ref.get(transaction=txn)
            if not code_doc.exists:
                raise KeyError("Invalid beta access code.")
            code_data = code_doc.to_dict() or {}
            if code_data.get("status") != "available":
                raise PermissionError("This beta access code is no longer available.")
            if code_data.get("assignedUserId") != uid:
                raise PermissionError("This beta access code does not belong to your account.")
            if profile.get("status") != "approved":
                raise PermissionError("Your beta application must be approved before you can redeem a code.")

            txn.set(
                user_ref,
                {
                    "betaProfile": {
                        **profile,
                        "status": "approved",
                        "accessCodeRedeemed": True,
                        "redeemedAt": now,
                        "applicationUpdatedAt": now,
                        "accessCodeId": code_ref.id,
                        "accessCodePreview": code_data.get("preview"),
                    }
                },
                merge=True,
            )
            txn.set(
                code_ref,
                {
                    "status": "redeemed",
                    "redeemedAt": now,
                    "redeemedBy": uid,
                },
                merge=True,
            )
            txn.set(
                application_ref,
                {
                    "status": "approved",
                    "accessCodeRedeemedAt": now,
                    "updatedAt": now,
                },
                merge=True,
            )

        _redeem(transaction)
