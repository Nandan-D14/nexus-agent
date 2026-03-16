"""Session management — maps session IDs to sandbox + agent state."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Optional

import jwt

from nexus.config import settings
from nexus.runtime_config import SessionRuntimeConfig
from nexus.sandbox import SandboxManager

if TYPE_CHECKING:
    from nexus.history_repository import FirestoreHistoryRepository

logger = logging.getLogger(__name__)


async def _maybe_mount_gdrive(
    session: "Session",
    repo: "FirestoreHistoryRepository",
) -> None:
    """If the user has a Google Drive refresh token, mount Google Drive in the sandbox via rclone."""
    try:
        user_settings = await repo.get_user_settings(session.owner_id)
    except Exception:
        return
    token: str | None = (user_settings or {}).get("googleDriveRefreshToken")
    if not token:
        return

    # rclone config block — token JSON expected by Drive backend
    token_json = (
        '{"access_token":"","token_type":"Bearer",'
        f'"refresh_token":"{token}",'
        '"expiry":"0001-01-01T00:00:00Z"}'
    )
    rclone_conf = f"[gdrive]\ntype = drive\ntoken = {token_json}\n"
    cmds = [
        # Install rclone if needed
        "command -v rclone >/dev/null 2>&1 || (curl -fsSL https://rclone.org/install.sh | bash -s -- --no-sudo 2>/dev/null)",
        f"mkdir -p ~/.config/rclone && printf '%s' {repr(rclone_conf)} > ~/.config/rclone/rclone.conf",
        "mkdir -p ~/gdrive",
        "rclone mount gdrive: ~/gdrive --daemon --vfs-cache-mode writes --allow-non-empty 2>/dev/null; true",
    ]
    loop = asyncio.get_running_loop()
    for cmd in cmds:
        try:
            await loop.run_in_executor(None, lambda c=cmd: session.sandbox.run_command(c, timeout=90))
        except Exception as exc:
            logger.warning("Google Drive mount cmd failed for session %s: %s", session.id, exc)
            return
    logger.info("Google Drive mounted at ~/gdrive for session %s", session.id)


@dataclass
class Session:
    """A single NEXUS session with its own sandbox and agent state."""

    id: str
    owner_id: str
    runtime_config: SessionRuntimeConfig
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

    async def create_session(
        self,
        owner_id: str,
        runtime_config: SessionRuntimeConfig,
    ) -> Session:
        """Create a session record. Sandbox boot is deferred until activation."""
        session_id = uuid.uuid4().hex[:12]
        session = Session(
            id=session_id,
            owner_id=owner_id,
            runtime_config=runtime_config,
            sandbox=SandboxManager(e2b_api_key=runtime_config.e2b_api_key),
        )

        self._sessions[session_id] = session
        await self._sync_session(session)
        logger.info("Session %s created and waiting for activation", session_id)
        return session

    async def ensure_session_ready(self, session_id: str) -> Session:
        """Boot (or resume) the sandbox for a session on first use."""
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

                # Try to resume a previously paused sandbox
                paused_id: str | None = None
                if self.history_repository:
                    try:
                        paused_id = await self.history_repository.get_persistent_sandbox(session.owner_id)
                    except Exception:
                        pass

                info: dict | None = None
                if paused_id:
                    try:
                        logger.info("Attempting sandbox resume for session %s (sandbox_id=%s)", session_id, paused_id)
                        info = await loop.run_in_executor(None, lambda: session.sandbox.resume(paused_id))
                        # Clear paused ID — it has been consumed
                        if self.history_repository:
                            try:
                                await self.history_repository.save_paused_sandbox(session.owner_id, None)
                            except Exception:
                                pass
                        logger.info("Session %s resumed from paused sandbox", session_id)
                    except Exception as exc:
                        logger.warning("Sandbox resume failed for session %s: %s. Creating new sandbox.", session_id, exc)
                        info = None

                if info is None:
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

            # Mount Google Drive if user has a refresh token configured
            if self.history_repository:
                await _maybe_mount_gdrive(session, self.history_repository)

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
        """Atomically check ownership and end the session.

        Pauses the E2B sandbox (preserving state) instead of destroying it, so
        the next session for this user can resume instantly.

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
            paused_id = await loop.run_in_executor(None, session.sandbox.pause)
            if paused_id and self.history_repository:
                try:
                    await self.history_repository.save_paused_sandbox(session.owner_id, paused_id)
                    logger.info("Session %s sandbox paused (sandbox_id=%s)", session_id, paused_id)
                except Exception:
                    logger.warning("Failed to save paused sandbox ID for session %s", session_id)
            elif not paused_id:
                # pause() failed — sandbox is gone, nothing to preserve
                pass
        session.status = "ended"
        await self._sync_session(
            session,
            status=status,
            ended_at=datetime.now(timezone.utc),
        )

    async def destroy_session(self, session_id: str, status: str = "ended", error_code: str | None = None) -> None:
        session = self._sessions.pop(session_id, None)
        if session and session.sandbox.is_alive:
            loop = asyncio.get_event_loop()
            if status in {"ended"} and self.history_repository:
                # Graceful end — pause so user can resume later
                paused_id = await loop.run_in_executor(None, session.sandbox.pause)
                if paused_id:
                    try:
                        await self.history_repository.save_paused_sandbox(session.owner_id, paused_id)
                    except Exception:
                        pass
            else:
                # Error/force-destroy — kill sandbox outright
                await loop.run_in_executor(None, session.sandbox.destroy)
            session.status = "ended" if status == "ended" else "destroyed"
            logger.info("Session %s %s", session_id, session.status)
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
        now = datetime.now(timezone.utc)
        payload = {
            "sid": session_id,
            "uid": owner_id,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    def validate_ticket(self, token: str) -> tuple[Optional[str], Optional[str]]:
        """Validate a WS ticket. Returns (session_id, owner_id) or (None, None)."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=["HS256"],
                leeway=30,
            )
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
