"""Firebase Admin app and Firestore client helpers."""

from __future__ import annotations

from functools import lru_cache

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore

from nexus.config import apply_runtime_env_overrides, settings


@lru_cache(maxsize=1)
def get_firebase_app():
    """Initialize Firebase Admin once using ADC or emulator config."""
    apply_runtime_env_overrides()

    project_id = settings.firebase_project_id or settings.google_project_id
    if not project_id:
        raise RuntimeError("Firebase project ID is not configured")

    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    try:
        return firebase_admin.initialize_app(options={"projectId": project_id})
    except ValueError:
        # Another thread/coroutine initialized the app concurrently
        return firebase_admin.get_app()


def get_firestore_client():
    return firestore.client(app=get_firebase_app())


def verify_id_token(id_token: str) -> dict:
    get_firebase_app()
    return firebase_auth.verify_id_token(id_token)
