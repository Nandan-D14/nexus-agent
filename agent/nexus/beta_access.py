"""Controlled beta access helpers."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, Mapping
from urllib.parse import quote

from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from nexus.config import settings

logger = logging.getLogger(__name__)

BetaState = Literal["none", "pending_review", "approved", "rejected", "revoked"]

_BETA_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def beta_access_enabled() -> bool:
    return bool(settings.beta_access_enabled)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_beta_profile(user_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = (
        dict(user_settings.get("betaProfile", {}))
        if isinstance(user_settings, Mapping) and isinstance(user_settings.get("betaProfile"), Mapping)
        else {}
    )
    raw_status = payload.get("status")
    status: BetaState = raw_status if raw_status in {"pending_review", "approved", "rejected", "revoked"} else "none"
    return {
        "status": status,
        "applicationId": payload.get("applicationId"),
        "applicationSubmittedAt": payload.get("applicationSubmittedAt"),
        "applicationUpdatedAt": payload.get("applicationUpdatedAt"),
        "approvedAt": payload.get("approvedAt"),
        "rejectedAt": payload.get("rejectedAt"),
        "revokedAt": payload.get("revokedAt"),
        "redeemedAt": payload.get("redeemedAt"),
        "accessCodeRedeemed": bool(payload.get("accessCodeRedeemed")),
        "accessCodeId": payload.get("accessCodeId"),
        "accessCodePreview": payload.get("accessCodePreview"),
        "lastDecisionBy": payload.get("lastDecisionBy"),
        "rejectionReason": payload.get("rejectionReason"),
        "revokedReason": payload.get("revokedReason"),
    }


def beta_can_access_app(profile: Mapping[str, Any]) -> bool:
    return profile.get("status") == "approved" and bool(profile.get("accessCodeRedeemed"))


def beta_needs_access_code(profile: Mapping[str, Any]) -> bool:
    return profile.get("status") == "approved" and not bool(profile.get("accessCodeRedeemed"))


def beta_can_apply(profile: Mapping[str, Any]) -> bool:
    return profile.get("status") in {"none", "rejected"}


def beta_status_message(profile: Mapping[str, Any]) -> str:
    status = profile.get("status")
    if status == "pending_review":
        return "Your beta application is pending review."
    if status == "approved" and not bool(profile.get("accessCodeRedeemed")):
        return "Your beta application was approved. Enter your beta access code to unlock the product."
    if status == "approved":
        return "Beta access is active for this account."
    if status == "rejected":
        return "Your beta application was not approved yet. Update the details and apply again."
    if status == "revoked":
        return "Beta access has been revoked for this account."
    return "Beta access is limited. Submit the application form before using CoComputer."


def build_beta_error_payload(profile: Mapping[str, Any]) -> dict[str, str]:
    status = profile.get("status")
    if status == "pending_review":
        return {
            "code": "BETA_APPROVAL_PENDING",
            "detail": beta_status_message(profile),
        }
    if status == "approved" and not bool(profile.get("accessCodeRedeemed")):
        return {
            "code": "BETA_ACCESS_CODE_REQUIRED",
            "detail": beta_status_message(profile),
        }
    if status == "revoked":
        return {
            "code": "BETA_ACCESS_REVOKED",
            "detail": beta_status_message(profile),
        }
    return {
        "code": "BETA_APPLICATION_REQUIRED",
        "detail": beta_status_message(profile),
    }


def hash_beta_access_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def generate_beta_access_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    blocks = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return f"NEX-{blocks[0]}-{blocks[1]}-{blocks[2]}"


def resolve_beta_admin_emails() -> set[str]:
    return {
        email.strip().lower()
        for email in settings.beta_admin_emails.split(",")
        if email.strip()
    }


def is_beta_admin(email: str | None) -> bool:
    if not email:
        return False
    return email.strip().lower() in resolve_beta_admin_emails()


def build_sheet_sync_state(status: Literal["pending", "synced", "error"], error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "updatedAt": utcnow(),
    }
    if error:
        payload["lastError"] = error[:500]
    else:
        payload["lastError"] = None
    if status == "synced":
        payload["syncedAt"] = utcnow()
    return payload


def build_beta_application_sheet_row(application: Mapping[str, Any]) -> list[str]:
    return [
        _format_sheet_value(application.get("submittedAt")),
        str(application.get("userId", "")),
        str(application.get("email", "")),
        str(application.get("fullName", "")),
        str(application.get("role", "")),
        str(application.get("companyTeam", "")),
        str(application.get("primaryUseCase", "")),
        str(application.get("currentWorkflow", "")),
        str(application.get("whyAccess", "")),
        str(application.get("expectedUsageFrequency", "")),
        str(application.get("status", "")),
        str(application.get("sheetSyncStatus", "")),
    ]


def append_beta_application_to_sheet(application: Mapping[str, Any]) -> None:
    spreadsheet_id = settings.beta_google_sheet_id.strip()
    sheet_name = settings.beta_google_sheet_name.strip() or "beta_applications"
    if not spreadsheet_id:
        raise RuntimeError("BETA_GOOGLE_SHEET_ID is not configured")

    session = AuthorizedSession(_build_google_credentials())
    target_range = quote(f"{sheet_name}!A:L", safe="!:$")
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{target_range}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
    )
    response = session.post(url, json={"values": [build_beta_application_sheet_row(application)]}, timeout=20)
    if response.status_code >= 400:
        logger.warning("Google Sheets sync failed: %s %s", response.status_code, response.text[:500])
        raise RuntimeError(f"Google Sheets sync failed with HTTP {response.status_code}")


def _build_google_credentials():
    if settings.google_application_credentials:
        return service_account.Credentials.from_service_account_file(
            settings.google_application_credentials,
            scopes=[_BETA_SHEETS_SCOPE],
        )
    credentials, _ = google_auth_default(scopes=[_BETA_SHEETS_SCOPE])
    return credentials


def _format_sheet_value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return "" if value is None else str(value)
