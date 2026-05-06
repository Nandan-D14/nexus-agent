# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Beta access endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.beta_access import (
    beta_access_enabled,
    beta_can_access_app,
    beta_can_apply,
    beta_needs_access_code,
    beta_status_message,
    build_beta_error_payload,
    build_sheet_sync_state,
    hash_beta_access_code,
    normalize_beta_profile,
    append_beta_application_to_sheet,
)
from nexus.config import settings
from nexus.runtime_config import get_byok_status
from nexus.dependencies import get_history_repository
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

class BetaApplicationRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    role: str = Field(..., min_length=2, max_length=100)
    company_team: str = Field(..., min_length=2, max_length=100)
    primary_use_case: str = Field(..., min_length=5, max_length=1000)
    current_workflow: str = Field(..., min_length=5, max_length=1000)
    why_access: str = Field(..., min_length=5, max_length=1000)
    expected_usage_frequency: str = Field(...)
    acknowledge_byok: bool = Field(...)

class BetaApplicationSummary(BaseModel):
    full_name: str
    email: str
    role: str
    company_team: str
    primary_use_case: str
    current_workflow: str
    why_access: str
    expected_usage_frequency: str
    acknowledge_byok: bool
    status: str
    sheet_sync_status: str | None = None

class BetaStatusResponse(BaseModel):
    state: str
    can_apply: bool
    can_access_app: bool
    needs_access_code: bool
    access_code_redeemed: bool
    requires_byok_setup: bool
    byok_missing: list[str]
    message: str
    application_submitted_at: datetime | None = None
    application_updated_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    revoked_at: datetime | None = None
    redeemed_at: datetime | None = None
    application: BetaApplicationSummary | None = None

class RedeemBetaAccessCodeRequest(BaseModel):
    code: str

def _serialize_beta_application(application: dict[str, Any] | None) -> BetaApplicationSummary | None:
    if not isinstance(application, dict):
        return None
    return BetaApplicationSummary(
        full_name=str(application.get("fullName", "")),
        email=str(application.get("email", "")),
        role=str(application.get("role", "")),
        company_team=str(application.get("companyTeam", "")),
        primary_use_case=str(application.get("primaryUseCase", "")),
        current_workflow=str(application.get("currentWorkflow", "")),
        why_access=str(application.get("whyAccess", "")),
        expected_usage_frequency=str(application.get("expectedUsageFrequency", "")),
        acknowledge_byok=bool(application.get("acknowledgeByok")),
        status=str(application.get("status", "none")),
        sheet_sync_status=(
            str(application.get("sheetSync", {}).get("status"))
            if isinstance(application.get("sheetSync"), dict) and application.get("sheetSync", {}).get("status")
            else None
        ),
    )

def _build_beta_status_response(
    *,
    user_settings: dict[str, Any] | None,
    application: dict[str, Any] | None = None,
) -> BetaStatusResponse:
    if not beta_access_enabled():
        byok_status = get_byok_status(user_settings)
        requires_byok_setup = bool((settings.require_byok or settings.beta_enforce_byok) and not byok_status.configured)
        return BetaStatusResponse(
            state="none",
            can_apply=False,
            can_access_app=True,
            needs_access_code=False,
            access_code_redeemed=False,
            requires_byok_setup=requires_byok_setup,
            byok_missing=list(byok_status.missing) if requires_byok_setup else [],
            message="Controlled beta access is disabled for now. This endpoint remains for future gated rollout.",
            application=None,
        )

    profile = normalize_beta_profile(user_settings)
    can_access_app = beta_can_access_app(profile)
    byok_status = get_byok_status(user_settings)
    requires_byok_setup = bool((settings.require_byok or settings.beta_enforce_byok) and can_access_app and not byok_status.configured)
    return BetaStatusResponse(
        state=profile["status"],
        can_apply=beta_can_apply(profile),
        can_access_app=can_access_app,
        needs_access_code=beta_needs_access_code(profile),
        access_code_redeemed=bool(profile.get("accessCodeRedeemed")),
        requires_byok_setup=requires_byok_setup,
        byok_missing=list(byok_status.missing) if requires_byok_setup else [],
        message=beta_status_message(profile),
        application_submitted_at=profile.get("applicationSubmittedAt"),
        application_updated_at=profile.get("applicationUpdatedAt"),
        approved_at=profile.get("approvedAt"),
        rejected_at=profile.get("rejectedAt"),
        revoked_at=profile.get("revokedAt"),
        redeemed_at=profile.get("redeemedAt"),
        application=_serialize_beta_application(application),
    )

@router.get("/api/v1/beta/status", response_model=BetaStatusResponse)
async def get_beta_status(user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    application = await history_repository.get_beta_application(user.uid)
    return _build_beta_status_response(user_settings=user_settings, application=application)

@router.post("/api/v1/beta/apply", response_model=BetaStatusResponse)
async def apply_for_beta(
    payload: BetaApplicationRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    if not beta_access_enabled():
        await history_repository.upsert_user(user)
        user_settings = await history_repository.get_user_settings(user.uid)
        return _build_beta_status_response(user_settings=user_settings, application=None)

    if not payload.acknowledge_byok:
        raise HTTPException(status_code=400, detail="You must acknowledge the BYOK requirement before applying.")

    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    profile = normalize_beta_profile(user_settings)

    if profile["status"] == "revoked":
        raise HTTPException(status_code=403, detail=build_beta_error_payload(profile))
    if profile["status"] == "pending_review":
        raise HTTPException(status_code=409, detail="Your beta application is already pending review.")
    if profile["status"] == "approved":
        raise HTTPException(
            status_code=409,
            detail="Your beta application is already approved. Redeem the access code or continue setup.",
        )

    now = datetime.now(timezone.utc)
    beta_application = {
        "userId": user.uid,
        "email": user.email or "",
        "fullName": payload.full_name.strip(),
        "role": payload.role.strip(),
        "companyTeam": payload.company_team.strip(),
        "primaryUseCase": payload.primary_use_case.strip(),
        "currentWorkflow": payload.current_workflow.strip(),
        "whyAccess": payload.why_access.strip(),
        "expectedUsageFrequency": payload.expected_usage_frequency.strip(),
        "acknowledgeByok": True,
        "status": "pending_review",
        "submittedAt": now,
        "updatedAt": now,
        "sheetSyncStatus": "pending",
        "sheetSync": build_sheet_sync_state("pending"),
    }
    await history_repository.upsert_beta_application(user.uid, beta_application)
    await history_repository.set_beta_profile(
        user.uid,
        {
            **profile,
            "status": "pending_review",
            "applicationId": user.uid,
            "applicationSubmittedAt": now,
            "applicationUpdatedAt": now,
            "approvedAt": None,
            "rejectedAt": None,
            "revokedAt": None,
            "redeemedAt": None,
            "accessCodeRedeemed": False,
            "accessCodeId": None,
            "accessCodePreview": None,
            "lastDecisionBy": None,
            "rejectionReason": None,
            "revokedReason": None,
        },
    )

    try:
        append_beta_application_to_sheet(beta_application)
        await history_repository.upsert_beta_application(
            user.uid,
            {
                "sheetSyncStatus": "synced",
                "sheetSync": build_sheet_sync_state("synced"),
            },
        )
    except Exception as exc:
        logger.warning("Beta application Sheets sync failed for %s: %s", user.uid, exc)
        await history_repository.upsert_beta_application(
            user.uid,
            {
                "sheetSyncStatus": "error",
                "sheetSync": build_sheet_sync_state("error", str(exc)),
            },
        )

    updated_user_settings = await history_repository.get_user_settings(user.uid)
    application = await history_repository.get_beta_application(user.uid)
    return _build_beta_status_response(user_settings=updated_user_settings, application=application)

@router.post("/api/v1/beta/redeem-code", response_model=BetaStatusResponse)
async def redeem_beta_access_code(
    payload: RedeemBetaAccessCodeRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    if not beta_access_enabled():
        await history_repository.upsert_user(user)
        user_settings = await history_repository.get_user_settings(user.uid)
        return _build_beta_status_response(user_settings=user_settings, application=None)

    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    profile = normalize_beta_profile(user_settings)

    if profile["status"] != "approved":
        raise HTTPException(status_code=403, detail=build_beta_error_payload(profile))
    if profile.get("accessCodeRedeemed"):
        application = await history_repository.get_beta_application(user.uid)
        return _build_beta_status_response(user_settings=user_settings, application=application)

    try:
        await history_repository.redeem_beta_access_code(user.uid, hash_beta_access_code(payload.code))
    except KeyError:
        raise HTTPException(
            status_code=403,
            detail={"code": "BETA_ACCESS_CODE_INVALID", "detail": "Invalid beta access code."},
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "BETA_ACCESS_CODE_INVALID", "detail": str(exc)},
        )

    updated_user_settings = await history_repository.get_user_settings(user.uid)
    application = await history_repository.get_beta_application(user.uid)
    return _build_beta_status_response(user_settings=updated_user_settings, application=application)
