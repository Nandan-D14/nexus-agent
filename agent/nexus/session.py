"""Session management — maps session IDs to sandbox + agent state."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import jwt

from nexus.config import settings
from nexus.sandbox import SandboxManager

if TYPE_CHECKING:
    from nexus.history_repository import FirestoreHistoryRepository

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A single NEXUS session with its own sandbox and agent state."""

    id: str
    owner_id: str
    sandbox: SandboxManager
    sandbox_id: str = ""
    stream_url: str = ""
    status: str = "idle"  # idle | creating | ready | active | error | destroyed
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activation_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        repr=False,
        compare=False,
    )

    def touch(self) -> None:
        """Update last_active timestamp."""
        self.last_active = datetime.now(timezone.utc)


class SessionManager:
    """Creates, tracks, and cleans up NEXUS sessions."""

    def __init__(self, history_repository: Optional["FirestoreHistoryRepository"] = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self.history_repository = history_repository

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    # ── CRUD ───────────────────────────────────────────────────

    async def create_session(self, owner_id: str) -> Session:
        """Create a session record. Sandbox boot is deferred until activation."""
        session_id = uuid.uuid4().hex[:12]
        session = Session(
            id=session_id,
            owner_id=owner_id,
            sandbox=SandboxManager(),
        )

        self._sessions[session_id] = session
        await self._sync_session(session)
        logger.info("Session %s created and waiting for activation", session_id)
        return session

    async def ensure_session_ready(self, session_id: str) -> Session:
        """Boot the sandbox for a session on first use."""
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)

        async with session.activation_lock:
            if session.sandbox.is_alive and session.stream_url:
                if session.status not in {"ready", "active"}:
                    session.status = "ready"
                    session.touch()
                    await self._sync_session(session, status="ready")
                return session

            session.status = "creating"
            session.touch()
            await self._sync_session(session, status="creating")

            try:
                loop = asyncio.get_running_loop()
                info = await loop.run_in_executor(None, session.sandbox.create)
            except Exception as exc:
                logger.exception("Failed to create sandbox for session %s", session_id)
                session.sandbox_id = ""
                session.stream_url = ""
                session.status = "error"
                await self._sync_session(
                    session,
                    status="error",
                    error_code="SANDBOX_INIT_ERROR",
                )
                raise RuntimeError(f"Sandbox creation failed: {exc}") from exc

            session.sandbox_id = info["sandbox_id"]
            session.stream_url = info["stream_url"]
            session.status = "ready"
            session.touch()
            await self._sync_session(session, status="ready")
            logger.info(
                "Session %s sandbox ready (stream_url=%s)",
                session_id,
                session.stream_url,
            )
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def list_sessions_for_owner(self, owner_id: str) -> list[Session]:
        sessions = [session for session in self._sessions.values() if session.owner_id == owner_id]
        sessions.sort(key=lambda session: session.last_active, reverse=True)
        return sessions

    async def destroy_if_owned(
        self, session_id: str, owner_id: str, status: str = "ended"
    ) -> None:
        """Atomically check ownership and destroy the session.

        Raises KeyError if the session is not found (already destroyed).
        Raises PermissionError if the session exists but is owned by someone else.
        """
        # No await before the pop, so this is atomic within the asyncio event loop.
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.owner_id != owner_id:
            raise PermissionError("Not the session owner")
        self._sessions.pop(session_id, None)
        if session.sandbox.is_alive:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.sandbox.destroy)
            session.status = "destroyed"
            logger.info("Session %s destroyed", session_id)
        await self._sync_session(
            session,
            status=status,
            ended_at=datetime.now(timezone.utc),
        )

    async def destroy_session(self, session_id: str, status: str = "ended", error_code: str | None = None) -> None:
        session = self._sessions.pop(session_id, None)
        if session and session.sandbox.is_alive:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.sandbox.destroy)
            session.status = "destroyed"
            logger.info("Session %s destroyed", session_id)
        if session:
            await self._sync_session(session, status=status, ended_at=datetime.now(timezone.utc), error_code=error_code)

    async def activate_session(self, session_id: str) -> Session:
        session = await self.ensure_session_ready(session_id)
        session.status = "active"
        session.touch()
        await self._sync_session(session, status="active")
        return session

    # ── Auth ───────────────────────────────────────────────────

    def create_ticket(self, session_id: str, owner_id: str) -> str:
        """Create a short-lived JWT for WebSocket authentication."""
        payload = {
            "sid": session_id,
            "uid": owner_id,
            "exp": datetime.now(timezone.utc).timestamp() + 120,  # 2 min
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    def validate_ticket(self, token: str) -> tuple[Optional[str], Optional[str]]:
        """Validate a WS ticket. Returns (session_id, owner_id) or (None, None)."""
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            return payload.get("sid"), payload.get("uid")
        except jwt.InvalidTokenError:
            return None, None

    # ── Cleanup ────────────────────────────────────────────────

    def start_cleanup(self) -> None:
        """Start the background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    def stop_cleanup(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()

    async def _cleanup_loop(self) -> None:
        """Destroy sessions that have been idle too long."""
        timeout = settings.session_timeout_minutes * 60
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            stale = [
                sid
                for sid, s in self._sessions.items()
                if (now - s.last_active).total_seconds() > timeout
            ]
            for sid in stale:
                logger.info("Cleaning up idle session %s", sid)
                await self.destroy_session(sid, status="ended")

    async def destroy_all(self) -> None:
        """Destroy every active session (used on shutdown)."""
        for sid in list(self._sessions.keys()):
            await self.destroy_session(sid, status="ended")

    async def _sync_session(
        self,
        session: Session,
        *,
        status: str | None = None,
        ended_at: datetime | None = None,
        error_code: str | None = None,
    ) -> None:
        if not self.history_repository:
            return
        try:
            await self.history_repository.upsert_session(
                session=session,
                status=status or session.status,
                ended_at=ended_at,
                error_code=error_code,
            )
        except Exception:
            logger.exception("Failed to mirror session %s into Firestore", session.id)
