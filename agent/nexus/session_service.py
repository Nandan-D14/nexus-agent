# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Firestore-backed implementation of the ADK SessionService."""

import copy
import logging
from typing import Any, Optional

from google.adk.events import Event
from google.adk.sessions import Session, State
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
import time

from nexus.firebase import get_firestore_client

logger = logging.getLogger(__name__)

class FirestoreSessionService(BaseSessionService):
    """ADK session service that reads/writes directly to Firestore.
    
    This replaces InMemorySessionService so that tool history and 
    thoughts are precisely reconstructed after process restart or
    WebSocket reconnect.
    """

    def __init__(self):
        super().__init__()
        self._db = get_firestore_client()

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
        
        # Save to firestore
        import asyncio
        data = session.model_dump(by_alias=True, mode="json")
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
        session = Session.model_validate(data)
        
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
            s = Session.model_validate(doc.to_dict())
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
        
        # In a highly optimized system, we could append to a subcollection.
        # For simplicity and given moderate event lengths, we update the whole doc.
        doc_ref = self._get_doc_ref(session.app_name, session.user_id, session.id)
        import asyncio
        data = session.model_dump(by_alias=True, mode="json")
        await asyncio.to_thread(doc_ref.set, data)
        
        return event
