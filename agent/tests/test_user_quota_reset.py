# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from nexus.config import settings
from nexus.repositories.user_repository import UserRepository
from scripts.reset_user_limits import reset_all_users


def test_starter_plan_defaults_matches_settings():
    now = datetime.now(timezone.utc)
    defaults = UserRepository._starter_plan_defaults(now)

    assert defaults["creditResetVersion"] == settings.default_credit_reset_version
    assert defaults["creditLimit"] == settings.default_credit_limit
    assert defaults["creditUsage"] == 0
    assert defaults["planId"] == settings.default_plan_id
    assert defaults["creditResetAt"] == now


def test_build_starter_plan_updates_triggers_reset_on_version_mismatch():
    now = datetime.now(timezone.utc)
    repo = UserRepository()

    # User with old reset version and accumulated usage
    stale_user_data = {
        "creditResetVersion": "old_version_20250101",
        "creditUsage": 3500,
        "creditLimit": 4000,
    }

    updates = repo._build_starter_plan_updates(stale_user_data, now=now)

    assert updates["creditResetVersion"] == settings.default_credit_reset_version
    assert updates["creditUsage"] == 0
    assert updates["creditLimit"] == settings.default_credit_limit
    assert updates["creditResetAt"] == now
    assert "migratedFromFreeTierAt" in updates


def test_build_starter_plan_updates_preserves_usage_when_version_matches():
    now = datetime.now(timezone.utc)
    repo = UserRepository()

    # User with current version and active usage
    current_user_data = {
        "planId": settings.default_plan_id,
        "planName": settings.default_plan_name,
        "planPriceUsd": settings.default_plan_price_usd,
        "planStatus": "active",
        "billingMode": "internal_entitlement",
        "creditLimit": settings.default_credit_limit,
        "creditUsage": 1200,
        "creditUnitUsd": settings.default_credit_unit_usd,
        "creditResetVersion": settings.default_credit_reset_version,
        "creditResetAt": now,
        "updatedAt": now,
        "migratedFromFreeTierAt": now,
    }

    updates = repo._build_starter_plan_updates(current_user_data, now=now)
    assert updates == {}


@patch("scripts.reset_user_limits.get_firestore_client")
def test_reset_all_users_script(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    mock_doc1 = MagicMock()
    mock_doc2 = MagicMock()
    mock_db.collection.return_value.stream.return_value = [mock_doc1, mock_doc2]

    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch

    count = reset_all_users(dry_run=False)

    assert count == 2
    assert mock_batch.update.call_count == 2
    assert mock_batch.commit.call_count == 1
