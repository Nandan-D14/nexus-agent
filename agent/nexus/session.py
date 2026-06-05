# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

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


async def _rehydrate_workspace_from_gcs(
    session: "Session",
    repo: "FirestoreHistoryRepository",
) -> None:
    """Restore workspace files from GCS into a fresh sandbox after snapshot expiry.

    This makes files permanently available — even if the E2B sandbox snapshot
    expired (>24 h), all files the agent previously wrote are pulled back from
    Google Cloud Storage so the agent can continue seamlessly.
    """
    try:
        from nexus.storage import get_storage_client

        run_ids: list[str] = []
        try:
            runs_ref = (
                repo._db.collection("sessions")
                .document(session.id)
                .collection("runs")
                .order_by("createdAt")
                .limit(50)
                .stream()
            )
            run_ids = [doc.id for doc in runs_ref]
        except Exception as exc:
            logger.warning("Rehydration: could not list runs for session %s: %s", session.id, exc)
            return

        if not run_ids:
            return

        artifacts = []
        for run_id in run_ids:
            try:
                batch = await repo.list_run_artifacts(session.id, run_id, limit=200)
                artifacts.extend(batch)
            except Exception as exc:
                logger.warning("Rehydration: could not list artifacts for run %s: %s", run_id, exc)

        if not artifacts:
            logger.info("Rehydration: no artifacts for session %s — nothing to restore", session.id)
            return

        SKIP_KINDS = {"screenshot", "image", "thumbnail"}
        gcs_client = get_storage_client()
        restored = 0
        skipped = 0

        for artifact in artifacts:
            if artifact.kind in SKIP_KINDS:
                skipped += 1
                continue

            meta = artifact.metadata or {}
            bucket_name = meta.get("gcs_bucket")
            blob_name = meta.get("gcs_blob")
            path = artifact.path

            if not bucket_name or not blob_name or not path:
                skipped += 1
                continue

            if not path.startswith("/"):
                skipped += 1
                continue

            try:
                content_bytes = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda b=bucket_name, n=blob_name: (
                        gcs_client.get_bucket(b).blob(n).download_as_bytes()
                    ),
                )
                session.sandbox.write_binary_file(path, content_bytes)
                restored += 1
                logger.debug("Rehydration: restored %s (%d bytes)", path, len(content_bytes))
            except Exception as exc:
                logger.warning("Rehydration: could not restore %s: %s", path, exc)
                skipped += 1

        logger.info(
            "Workspace rehydration complete for session %s — restored %d files, skipped %d",
            session.id, restored, skipped,
        )
    except Exception as exc:
        logger.warning("Workspace rehydration failed for session %s (non-fatal): %s", session.id, exc)


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
    """A single CoComputer session with its own sandbox and agent state."""

    id: str
    owner_id: str
    runtime_config: SessionRuntimeConfig
    sandbox: SandboxManager
    task_id: str = ""
    resume_mode: str = "fresh"
    resume_source_session_id: str | None = None
    seed_context: str = ""
    initial_title: str = "New session"
    current_run_id: str | None = None
    run_status: str = "queued"
    artifact_count: int = 0
    can_continue_conversation: bool = True
    exact_workspace_resume_available: bool = False
    continuation_mode: str | None = None
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


import redis
import json

class SessionManager:
    """Creates, tracks, and cleans up CoComputer sessions."""

    def __init__(self, history_repository: Optional["FirestoreHistoryRepository"] = None) -> None:
        self._in_memory_locks: dict[str, asyncio.Lock] = {}
        self._local_sessions: dict[str, Session] = {}
        self._redis: Optional[redis.Redis] = None
        if settings.redis_url:
            try:
                self._redis = redis.from_url(settings.redis_url)
                logger.info("SessionManager connected to Redis for distributed state.")
            except Exception:
                logger.warning("Failed to connect to Redis for SessionManager; using local state only.")
        self._cleanup_task: Optional[asyncio.Task] = None
        self._idle_pause_tasks: dict[str, asyncio.Task] = {}
        self.history_repository = history_repository

    @property
    def active_count(self) -> int:
        if self._redis:
            try:
                return self._redis.hlen("nexus:sessions")
            except Exception:
                pass
        return len(self._local_sessions)

    # ── CRUD ───────────────────────────────────────────────────

    async def create_session(
        self,
        owner_id: str,
        runtime_config: SessionRuntimeConfig,
        *,
        resume_mode: str = "fresh",
        resume_source_session_id: str | None = None,
        seed_context: str = "",
        initial_title: str = "New session",
        session_id: str | None = None,
        task_id: str | None = None,
        created_at: datetime | None = None,
        artifact_count: int = 0,
        exact_workspace_resume_available: bool = False,
        continuation_mode: str | None = None,
    ) -> Session:
        """Create a session record. Sandbox boot is deferred until activation."""
        session_id = session_id or uuid.uuid4().hex[:12]
        task_id = task_id or session_id
        session = Session(
            id=session_id,
            owner_id=owner_id,
            runtime_config=runtime_config,
            sandbox=SandboxManager(e2b_api_key=runtime_config.e2b_api_key),
            task_id=task_id,
            resume_mode=resume_mode,
            resume_source_session_id=resume_source_session_id,
            seed_context=seed_context,
            initial_title=initial_title,
            created_at=created_at or datetime.now(timezone.utc),
            artifact_count=artifact_count,
            exact_workspace_resume_available=exact_workspace_resume_available,
            continuation_mode=continuation_mode,
        )

        self._local_sessions[session_id] = session
        if self._redis:
            try:
                metadata = {
                    "id": session.id,
                    "owner_id": session.owner_id,
                    "status": session.status,
                    "created_at": session.created_at.isoformat(),
                    "task_id": session.task_id,
                }
                self._redis.hset("nexus:sessions", session_id, json.dumps(metadata))
                self._redis.expire("nexus:sessions", 7200)
            except Exception:
                logger.warning("Failed to sync session %s to Redis", session_id, exc_info=True)

        await self._sync_session(session)
        if self.history_repository:
            try:
                run = await self.history_repository.create_run(
                    session_id=session.id,
                    owner_id=session.owner_id,
                    title=session.initial_title,
                    source_session_id=session.resume_source_session_id,
                )
                session.current_run_id = run.run_id
                session.run_status = run.status
                session.artifact_count = run.artifact_count
                await self._sync_session(session)
            except Exception:
                logger.exception("Failed to create initial run for session %s", session_id)
        logger.info("Session %s created and waiting for activation", session_id)
        return session

    async def continue_session(
        self,
        *,
        session_id: str,
        owner_id: str,
        runtime_config: SessionRuntimeConfig,
        created_at: datetime,
        resume_mode: str,
        seed_context: str,
        initial_title: str,
        task_id: str | None = None,
        artifact_count: int = 0,
        exact_workspace_resume_available: bool = False,
        continuation_mode: str | None = None,
    ) -> Session:
        """Rehydrate an existing stored thread into a live session with the same ID."""
        existing = self._local_sessions.get(session_id)
        if existing:
            if existing.owner_id != owner_id:
                raise PermissionError("Not the session owner")
            return existing

        session = await self.create_session(
            owner_id=owner_id,
            runtime_config=runtime_config,
            resume_mode=resume_mode,
            resume_source_session_id=session_id,
            seed_context=seed_context,
            initial_title=initial_title,
            session_id=session_id,
            task_id=task_id or session_id,
            created_at=created_at,
            artifact_count=artifact_count,
            exact_workspace_resume_available=exact_workspace_resume_available,
            continuation_mode=continuation_mode,
        )
        return session

    async def ensure_session_ready(self, session_id: str) -> Session:
        """Boot (or resume) the sandbox for a session on first use."""
        session = self._local_sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)

        self.cancel_idle_pause(session_id)

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
                if self.history_repository and session.resume_mode == "continue_latest_workspace":
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
                                await self.history_repository.save_paused_sandbox(session.owner_id, None, None)
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

            # Rehydrate workspace files from GCS on resume (best-effort, non-fatal).
            # Covers the case where the E2B snapshot expired (>24h) — all files
            # are restored from permanent GCS storage so the agent can continue.
            if self.history_repository and session.resume_mode in {
                "continue_latest_workspace",
                "continue_conversation",
            }:
                await _rehydrate_workspace_from_gcs(session, self.history_repository)

            # Mount Google Drive if user has a refresh token configured
            if self.history_repository:
                await _maybe_mount_gdrive(session, self.history_repository)

            logger.info(
                "Session %s sandbox ready (stream_url=%s)",
                session_id,
                session.stream_url,
            )
            return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        # Check local first (active handles)
        local = self._local_sessions.get(session_id)
        if local:
            return local

        if not self.history_repository:
            return None
        stored = await self.history_repository.get_session(session_id)
        if not stored:
            return None
        # We return a dummy session with just the ID, owner, etc since we can't reconstruct runtime_config here
        # The true reconstruction happens in endpoints that receive the user object or WS ticket validation
        # Wait, for the websocket reconnect, SandboxManager only needs the sandbox_id.
        session = Session(
            id=session_id,
            owner_id=stored.owner_id,
            runtime_config=None, # type: ignore
            sandbox=SandboxManager(),
            task_id=stored.task_id,
            status=stored.status,
            sandbox_id=stored.sandbox_id or "",
            resume_mode="fresh"
        )
        # Note: this dummy session is NOT added to _local_sessions until activation
        return session



    def list_sessions_for_owner(self, owner_id: str) -> list[Session]:
        sessions = [session for session in self._local_sessions.values() if session.owner_id == owner_id]
        sessions.sort(key=lambda session: session.last_active, reverse=True)
        return sessions

    async def destroy_if_owned(
        self, session_id: str, owner_id: str, status: str = "ended"
    ) -> None:
        """Atomically check ownership and end the session."""
        session = self._local_sessions.get(session_id)
        if session is None:
            # Check if it exists in history to provide better errors
            if self.history_repository:
                stored = await self.history_repository.get_session(session_id)
                if stored and stored.owner_id != owner_id:
                    raise PermissionError("Not the session owner")
            raise KeyError(session_id)
            
        if session.owner_id != owner_id:
            raise PermissionError("Not the session owner")
        
        await self.destroy_session(session_id, status=status)

    async def destroy_session(self, session_id: str, status: str = "ended", error_code: str | None = None) -> None:
        scheduled_pause = self._idle_pause_tasks.pop(session_id, None)
        current_task = asyncio.current_task()
        if scheduled_pause and scheduled_pause is not current_task and not scheduled_pause.done():
            scheduled_pause.cancel()

        session = self._local_sessions.pop(session_id, None)
        if self._redis:
            try:
                self._redis.hdel("nexus:sessions", session_id)
            except Exception:
                pass

        paused_id: str | None = None
        if session and session.sandbox.is_alive:
            loop = asyncio.get_event_loop()
            if status in {"ended"} and self.history_repository:
                # Graceful end — pause so user can resume later
                paused_id = await loop.run_in_executor(None, session.sandbox.pause)
                if paused_id:
                    try:
                        await self.history_repository.save_paused_sandbox(session.owner_id, paused_id, session.id)
                    except Exception:
                        pass
            else:
                # Error/force-destroy — kill sandbox outright
                await loop.run_in_executor(None, session.sandbox.destroy)
            session.status = "ended" if status == "ended" else "destroyed"
            logger.info("Session %s %s", session_id, session.status)
        
        if session:
            await self._sync_session(session, status=status, ended_at=datetime.now(timezone.utc), error_code=error_code)
            if self.history_repository:
                try:
                    await self.history_repository.refresh_session_handoff(
                        session.id,
                        owner_id=session.owner_id,
                        resume_state="paused" if paused_id else status,
                        workspace_owner_session_id=session.id if paused_id else None,
                        can_continue_workspace=bool(paused_id),
                    )
                except Exception:
                    logger.warning("Failed to refresh handoff summary for session %s", session_id, exc_info=True)

    async def activate_session(self, session_id: str) -> Session:
        self.cancel_idle_pause(session_id)
        session = await self.ensure_session_ready(session_id)
        session.status = "active"
        session.touch()
        await self._sync_session(session, status="active")
        return session

    def cancel_idle_pause(self, session_id: str) -> None:
        """Cancel a delayed idle pause, usually because the browser reconnected."""
        task = self._idle_pause_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def schedule_idle_pause(self, session_id: str, *, delay_seconds: int | None = None) -> None:
        """Pause an idle sandbox after a reconnect grace period."""
        self.cancel_idle_pause(session_id)
        delay = settings.idle_sandbox_pause_seconds if delay_seconds is None else delay_seconds
        delay = max(int(delay), 0)
        task = asyncio.create_task(self._idle_pause_after_delay(session_id, delay))
        self._idle_pause_tasks[session_id] = task

    async def _idle_pause_after_delay(self, session_id: str, delay_seconds: int) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            session = self._local_sessions.get(session_id)
            if not session or session.status in {"destroyed", "ended", "error"}:
                return
            if not session.sandbox.is_alive:
                return
            idle_for = (datetime.now(timezone.utc) - session.last_active).total_seconds()
            if idle_for < delay_seconds:
                return
            logger.info("Pausing idle sandbox after reconnect grace for session %s", session_id)
            await self.destroy_session(session_id, status="ended")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to pause idle sandbox for session %s", session_id, exc_info=True)
        finally:
            current_task = asyncio.current_task()
            if self._idle_pause_tasks.get(session_id) is current_task:
                self._idle_pause_tasks.pop(session_id, None)

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
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session cleanup loop started")

    def stop_cleanup(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("Session cleanup loop stopped")
        for task in self._idle_pause_tasks.values():
            if not task.done():
                task.cancel()
        self._idle_pause_tasks.clear()
    async def _cleanup_loop(self) -> None:
        """Destroy sessions that have been idle too long."""
        timeout = settings.session_timeout_minutes * 60
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            stale = [
                sid
                for sid, s in self._local_sessions.items()
                if (now - s.last_active).total_seconds() > timeout
            ]
            for sid in stale:
                logger.info("Cleaning up idle session %s", sid)
                await self.destroy_session(sid, status="ended")

    async def destroy_all(self) -> None:
        """Destroy every active session (used on shutdown)."""
        for sid in list(self._local_sessions.keys()):
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
