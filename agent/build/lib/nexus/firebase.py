"""Firebase Admin app and Firestore client helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials as firebase_credentials
from firebase_admin import firestore

from nexus.config import AGENT_DIR, WORKSPACE_DIR, apply_runtime_env_overrides, settings


def _resolve_credentials_path(raw_path: str) -> Path:
    """Resolve Firebase Admin credential paths independently of cwd."""
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate

    search_roots = (
        Path.cwd(),
        AGENT_DIR,
        WORKSPACE_DIR,
    )
    for root in search_roots:
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved

    searched = ", ".join(str((root / candidate).resolve()) for root in search_roots)
    raise RuntimeError(
        f"Firebase Admin credentials file was not found. Looked for: {searched}"
    )


@lru_cache(maxsize=1)
def get_firebase_app():
    """Initialize Firebase Admin once.

    Uses explicit service-account credentials when a key file is configured,
    so that GOOGLE_APPLICATION_CREDENTIALS is NOT set globally (which would
    leak the Firebase SA into the Vertex AI / genai SDK and cause 403s).
    Falls back to ADC when no key file is provided (e.g. on Cloud Run where
    the Compute Engine SA handles both Firebase and Vertex AI).
    """
    apply_runtime_env_overrides()

    project_id = settings.firebase_project_id
    if not project_id:
        raise RuntimeError("Firebase project ID is not configured")

    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    # Build credential: explicit key file if available, otherwise ADC
    cred = None
    if settings.google_application_credentials:
        cred_path = _resolve_credentials_path(settings.google_application_credentials)
        cred = firebase_credentials.Certificate(str(cred_path))

    try:
        return firebase_admin.initialize_app(
            credential=cred,
            options={"projectId": project_id},
        )
    except ValueError:
        # Another thread/coroutine initialized the app concurrently
        return firebase_admin.get_app()


def get_firestore_client():
    return firestore.client(app=get_firebase_app())


def verify_id_token(id_token: str) -> dict:
    get_firebase_app()
    return firebase_auth.verify_id_token(id_token)
