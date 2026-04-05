"""FastAPI authentication helpers backed by Firebase ID tokens."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Annotated

from firebase_admin import auth as firebase_auth
from google.auth.exceptions import DefaultCredentialsError
from fastapi import Header, HTTPException, status

from nexus.config import settings
from nexus.firebase import verify_id_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


def _decode_jwt_segment(segment: str) -> dict[str, object] | None:
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(f"{segment}{padding}")
        decoded = json.loads(raw)
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def _describe_unverified_token(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3:
        return "malformed JWT"

    header = _decode_jwt_segment(parts[0]) or {}
    payload = _decode_jwt_segment(parts[1]) or {}
    if not header and not payload:
        return None

    fields: list[str] = []
    for key in ("alg", "kid"):
        value = header.get(key)
        if isinstance(value, str) and value:
            fields.append(f"{key}={value}")

    for key in ("aud", "iss", "sub"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            fields.append(f"{key}={value}")

    for key in ("iat", "exp", "auth_time"):
        value = payload.get(key)
        if isinstance(value, int):
            fields.append(f"{key}={value}")

    return ", ".join(fields) if fields else None


def _invalid_token_detail(token: str, exc: Exception) -> str:
    detail = "Invalid Firebase ID token"
    if settings.is_production:
        return detail

    reason = str(exc).strip()
    observed = _describe_unverified_token(token)
    parts = [detail]
    if reason:
        parts.append(reason)
    if observed:
        parts.append(f"token={observed}")
    parts.append(f"expected_project={settings.firebase_project_id}")
    return " | ".join(parts)


def _parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")

    return token


async def require_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    token = _parse_bearer_token(authorization)

    try:
        claims = verify_id_token(token)
    except DefaultCredentialsError as exc:
        logger.error("Firebase Admin credentials are not available", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase Admin credentials are not configured",
        ) from exc
    except RuntimeError as exc:
        logger.error("Firebase token verification service error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error verifying Firebase ID token",
        ) from exc
    except (
        firebase_auth.InvalidIdTokenError,
        firebase_auth.ExpiredIdTokenError,
        firebase_auth.RevokedIdTokenError,
        firebase_auth.UserDisabledError,
    ) as exc:
        logger.warning(
            "Firebase ID token rejected: %s | expected_project=%s | token=%s",
            exc,
            settings.firebase_project_id,
            _describe_unverified_token(token),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_invalid_token_detail(token, exc),
        ) from exc
    except Exception as exc:
        logger.error("Unexpected Firebase token verification failure", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error verifying Firebase ID token",
        ) from exc

    uid = claims.get("uid")
    if not uid:
        logger.error("Firebase token claims missing 'uid': %s", list(claims.keys()))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firebase ID token")

    return AuthenticatedUser(
        uid=uid,
        email=claims.get("email"),
        display_name=claims.get("name"),
        photo_url=claims.get("picture"),
    )
