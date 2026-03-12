"""FastAPI authentication helpers backed by Firebase ID tokens."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

from nexus.firebase import verify_id_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


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
    except RuntimeError as exc:
        logger.error("Firebase token verification service error", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error verifying Firebase ID token") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firebase ID token") from exc

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
