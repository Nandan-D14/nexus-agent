# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""At-rest encryption for integration credentials stored in Firestore.

Private integration docs hold OAuth tokens, PATs and API keys. They are sealed
with the same Fernet key as BYOK credentials. Values carry a version prefix so
sealing is idempotent and legacy plaintext docs keep working: they are read as
plaintext and encrypted the next time the connection is written.
"""

from __future__ import annotations

import logging
from typing import Any

from nexus.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

SEALED_PREFIX = "enc:v1:"
SECRET_FIELDS = frozenset({
    "token",
    "apiKey",
    "bearerToken",
    "accessToken",
    "refreshToken",
    "oauthClientSecret",
    "googleDriveRefreshToken",
})
# Header values (e.g. ``x-api-key``) are secrets too.
SECRET_MAP_FIELDS = frozenset({"extraHeaders"})


def seal_value(value: Any) -> Any:
    if not isinstance(value, str) or not value or value.startswith(SEALED_PREFIX):
        return value
    return SEALED_PREFIX + encrypt_secret(value)


def open_value(value: Any) -> Any:
    if not isinstance(value, str) or not value.startswith(SEALED_PREFIX):
        return value
    try:
        return decrypt_secret(value[len(SEALED_PREFIX):])
    except RuntimeError:
        # Wrong/rotated key: surface as "no credential" so the connector shows
        # as needing re-auth instead of crashing every turn.
        logger.warning("Stored integration credential could not be decrypted")
        return ""


def _map(payload: dict[str, Any], fn) -> dict[str, Any]:
    result = dict(payload)
    for key in SECRET_FIELDS:
        if key in result:
            result[key] = fn(result[key])
    for key in SECRET_MAP_FIELDS:
        value = result.get(key)
        if isinstance(value, dict):
            result[key] = {name: fn(item) for name, item in value.items()}
    return result


def seal_private(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with credential fields encrypted."""
    return _map(payload, seal_value)


def open_private(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of ``payload`` with credential fields decrypted."""
    return _map(payload or {}, open_value)
