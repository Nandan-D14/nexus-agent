# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Firestore-backed implementation of the ADK SessionService."""

import copy
import logging
import uuid
from typing import Any, Optional

from google.adk.events import Event
from google.adk.sessions import Session, State
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from pydantic import ValidationError
import time

from nexus.firebase import get_firestore_client

logger = logging.getLogger(__name__)

# #region agent log
def _dbg(hid: str, loc: str, msg: str, data: dict | None = None) -> None:
    import json, urllib.request
    payload = {"sessionId": "19cd7e", "hypothesisId": hid, "location": loc, "message": msg, "data": data or {}, "timestamp": int(time.time() * 1000), "runId": "post-fix"}
    try:
        with open(r"c:\Users\nanda\OneDrive\Desktop\co-computer\debug-19cd7e.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:7421/ingest/08b059be-2c03-45ae-97a1-bb3c6f862ec1",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Debug-Session-Id": "19cd7e"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=0.3).read()
    except Exception:
        pass
# #endregion


_REMOVED_PART_KEYS = {
    "audioTranscription",
    "audio_transcription",
}


def _sanitize_adk_value(value: Any) -> Any:
    """Drop Part extras ADK no longer accepts (e.g. audioTranscription: null)."""
    if isinstance(value, list):
        return [_sanitize_adk_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sanitize_adk_value(item)
        for key, item in value.items()
        if key not in _REMOVED_PART_KEYS
    }


def _delete_path(root: dict[str, Any], loc: tuple[Any, ...]) -> bool:
    current: Any = root
    for index, key in enumerate(loc):
        last = index == len(loc) - 1
        if isinstance(current, list):
            if not isinstance(key, int) or key < 0 or key >= len(current):
                return False
            if last:
                return False
            current = current[key]
        elif isinstance(current, dict):
            if last:
                if key in current:
                    del current[key]
                    return True
                return False
            current = current.get(key)
            if current is None:
                return False
        else:
            return False
    return False


def _validate_adk_session(data: dict[str, Any]) -> Session:
    payload = _sanitize_adk_value(copy.deepcopy(data))
    if not isinstance(payload, dict):
        raise TypeError("ADK session payload must be an object")
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    raw_events = data.get("events") if isinstance(data.get("events"), list) else []
    # #region agent log
    _dbg("F", "session_service.py:_validate_adk_session", "validate_session", {
        "event_n": len(events),
        "had_audio_transcription": any(
            isinstance(event, dict)
            and isinstance(event.get("content"), dict)
            and any(
                isinstance(part, dict) and "audioTranscription" in part
                for part in (event.get("content") or {}).get("parts") or []
            )
            for event in raw_events
            if isinstance(event, dict)
        ),
    })
    # #endregion
    last_error: ValidationError | None = None
    for _ in range(16):
        try:
            return Session.model_validate(payload)
        except ValidationError as exc:
            last_error = exc
            stripped = False
            extras: list[str] = []
            for err in exc.errors():
                if err.get("type") != "extra_forbidden":
                    continue
                loc = tuple(err.get("loc") or ())
                extras.append(".".join(str(part) for part in loc))
                if _delete_path(payload, loc):
                    stripped = True
            if extras:
                # #region agent log
                _dbg("F", "session_service.py:_validate_adk_session", "stripped_extra", {
                    "extras": extras[:8],
                })
                # #endregion
            if not stripped:
                raise
    if last_error is not None:
        raise last_error
    return Session.model_validate(payload)


class FirestoreSessionService(BaseSessionService):
    """ADK session service that reads/writes directly to Firestore.
    
    This replaces InMemorySessionService so that tool history and 
    thoughts are precisely reconstructed after process restart or
    WebSocket reconnect.
    """

    def __init__(self, db: Any = None):
        super().__init__()
        self._custom_db = db

    @property
    def _db(self):
        if self._custom_db is not None:
            return self._custom_db
        return get_firestore_client()

    @_db.setter
    def _db(self, value: Any) -> None:
        self._custom_db = value

    def _get_doc_ref(self, app_name: str, user_id: str, session_id: str):
        return self._db.collection("adk_sessions").document(f"{app_name}_{user_id}_{session_id}")

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        # In a real implementation we would merge app/user state,
        # but for CoComputer ADK, we mainly rely on session state.
        
        if not session_id:
            import uuid
            session_id = uuid.uuid4().hex
            
        doc_ref = self._get_doc_ref(app_name, user_id, session_id)
        
        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=state or {},
            events=[],
            last_update_time=time.time(),
        )
        
        # Save metadata to Firestore. Events are stored append-only in a
        # subcollection so the session document does not grow without bound.
        import asyncio
        data = session.model_dump(by_alias=True, mode="json", exclude_none=True)
        data["events"] = []
        await asyncio.to_thread(doc_ref.set, data)
        
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        
        doc_ref = self._get_doc_ref(app_name, user_id, session_id)
        
        import asyncio
        doc = await asyncio.to_thread(doc_ref.get)
        
        if not doc.exists:
            return None
            
        data = doc.to_dict()
        embedded_events = data.get("events") if isinstance(data.get("events"), list) else []
        event_docs = await asyncio.to_thread(
            lambda: list(doc_ref.collection("events").order_by("timestamp").stream())
        )
        if event_docs:
            data["events"] = [event_doc.to_dict() or {} for event_doc in event_docs]
        else:
            data["events"] = embedded_events
        session = _validate_adk_session(data)
        
        if config:
            if config.num_recent_events:
                session.events = session.events[-config.num_recent_events :]
            if config.after_timestamp:
                i = len(session.events) - 1
                while i >= 0:
                    if session.events[i].timestamp < config.after_timestamp:
                        break
                    i -= 1
                if i >= 0:
                    session.events = session.events[i + 1 :]
                    
        return session

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        # For our use-case, this isn't strictly required since we rely on HistoryRepository.
        # But we implement a basic variant just in case.
        import asyncio
        query = self._db.collection("adk_sessions").where("appName", "==", app_name)
        if user_id:
            query = query.where("userId", "==", user_id)
            
        docs = await asyncio.to_thread(query.get)
        sessions = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["events"] = []
            s = _validate_adk_session(data)
            s.events = [] # Following in-memory pattern which drops events for list
            sessions.append(s)
            
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        doc_ref = self._get_doc_ref(app_name, user_id, session_id)
        import asyncio
        await asyncio.to_thread(doc_ref.delete)

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event
            
        # Perform temp state cleanup using the base class methods.
        await super().append_event(session=session, event=event)
        session.last_update_time = event.timestamp
        
        # Append event to a subcollection and keep the parent document compact.
        doc_ref = self._get_doc_ref(session.app_name, session.user_id, session.id)
        import asyncio
        event_id = (
            getattr(event, "id", None)
            or getattr(event, "event_id", None)
            or uuid.uuid4().hex
        )
        event_data = event.model_dump(by_alias=True, mode="json", exclude_none=True)
        data = session.model_dump(by_alias=True, mode="json", exclude_none=True)
        data["events"] = []
        await asyncio.to_thread(
            lambda: (
                doc_ref.collection("events").document(str(event_id)).set(event_data),
                doc_ref.set(data, merge=True),
            )
        )
        
        return event
