# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from nexus.auth import require_current_user
from firebase_admin import auth as firebase_auth

@pytest.mark.asyncio
async def test_auth_expired_token():
    """Verify that an expired Firebase token returns a 401 Unauthorized error."""
    with patch("nexus.auth.verify_id_token") as mock_verify:
        mock_verify.side_effect = firebase_auth.ExpiredIdTokenError("Token expired", MagicMock())
        
        with pytest.raises(HTTPException) as exc:
            await require_current_user(authorization="Bearer expired-token")
        
        assert exc.value.status_code == 401
        assert "Invalid Firebase ID token" in exc.value.detail

@pytest.mark.asyncio
async def test_auth_firebase_unavailable():
    """Verify that a service error from Firebase returns a 503 Service Unavailable error."""
    with patch("nexus.auth.verify_id_token") as mock_verify:
        # Simulate a generic RuntimeError or service failure
        mock_verify.side_effect = RuntimeError("Service unreachable")
        
        with pytest.raises(HTTPException) as exc:
            await require_current_user(authorization="Bearer some-token")
        
        assert exc.value.status_code == 503
        assert "Error verifying Firebase ID token" in exc.value.detail

@pytest.mark.asyncio
async def test_auth_missing_header():
    """Verify that missing authorization header returns 401."""
    with pytest.raises(HTTPException) as exc:
        await require_current_user(authorization=None)
    assert exc.value.status_code == 401


def test_missing_firebase_credentials_path_falls_back_in_dev(monkeypatch):
    """A stale local GOOGLE_APPLICATION_CREDENTIALS path should not break dev auth init."""
    import firebase_admin
    from nexus import firebase as firebase_module

    firebase_module.get_firebase_app.cache_clear()
    monkeypatch.setattr(firebase_module.settings, "google_application_credentials", "missing-admin-key.json")
    monkeypatch.setattr(firebase_module.settings, "firebase_project_id", "test-project")
    monkeypatch.setattr(firebase_module.settings, "app_env", "development")
    monkeypatch.setattr(firebase_admin, "get_app", MagicMock(side_effect=ValueError()))
    initialize_app = MagicMock(return_value="app")
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize_app)

    assert firebase_module.get_firebase_app() == "app"
    assert initialize_app.call_args.kwargs["credential"] is None
