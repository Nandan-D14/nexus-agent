# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Encryption helpers for stored BYO keys."""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from nexus.config import settings

logger = logging.getLogger(__name__)


def _is_local_development() -> bool:
    return settings.frontend_url.startswith(("http://localhost", "http://127.0.0.1"))


def _derive_local_dev_key() -> str:
    seed = "|".join(
        (
            settings.jwt_secret or "dev-secret-change-in-production",
            settings.frontend_url,
            settings.firebase_project_id,
            settings.google_project_id,
        )
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


@lru_cache(maxsize=1)
def get_byok_fernet() -> Fernet:
    key = settings.byok_encryption_key.strip()
    if not key:
        if not _is_local_development():
            raise RuntimeError("BYOK_ENCRYPTION_KEY is not configured")
        key = _derive_local_dev_key()
        logger.warning(
            "BYOK_ENCRYPTION_KEY is not configured; using a deterministic local-development fallback. "
            "Set BYOK_ENCRYPTION_KEY explicitly before production."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        # If key is not valid 32-byte urlsafe base64, hash and derive a valid Fernet key
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        derived = base64.urlsafe_b64encode(digest).decode("utf-8")
        return Fernet(derived.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    return get_byok_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return get_byok_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored BYOK credential could not be decrypted. Re-save the key."
        ) from exc
