# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Long-lived agent memory (production stack Layer 4).

Stores durable user-scoped facts in Firestore under
``users/{owner_id}/memory_facts/{fact_id}``. Facts are injected into each
turn's context by the context builder (budget-capped) and written by the
``remember_fact`` tool or future extraction pipelines.

Kept intentionally simple: no embeddings, no vector store. Recency-ordered
facts with a hard cap cover the "remember my preferences / project details"
production use case without new infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from nexus.config import settings

logger = logging.getLogger(__name__)

_MAX_FACT_CHARS = 500


@dataclass(frozen=True)
class MemoryFact:
    fact_id: str
    owner_id: str
    text: str
    category: str
    created_at: datetime
    session_id: str | None = None


class MemoryStore:
    """Firestore-backed store for user memory facts."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _db(self):
        if self._client is None:
            from nexus.firebase import get_firestore_client

            self._client = get_firestore_client()
        return self._client

    def _facts_collection(self, owner_id: str):
        return self._db().collection("users").document(owner_id).collection("memory_facts")

    async def add_fact(
        self,
        *,
        owner_id: str,
        text: str,
        category: str = "general",
        session_id: str | None = None,
    ) -> MemoryFact:
        return await asyncio.to_thread(
            self._add_fact_sync, owner_id, text, category, session_id
        )

    def _add_fact_sync(
        self,
        owner_id: str,
        text: str,
        category: str,
        session_id: str | None,
    ) -> MemoryFact:
        cleaned = " ".join(str(text or "").split())[:_MAX_FACT_CHARS]
        if not cleaned:
            raise ValueError("Memory fact text is empty.")
        fact_id = f"fact_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        payload = {
            "factId": fact_id,
            "ownerId": owner_id,
            "text": cleaned,
            "category": str(category or "general").strip().lower()[:40] or "general",
            "sessionId": session_id,
            "createdAt": now,
        }
        self._facts_collection(owner_id).document(fact_id).set(payload)
        return MemoryFact(
            fact_id=fact_id,
            owner_id=owner_id,
            text=cleaned,
            category=payload["category"],
            created_at=now,
            session_id=session_id,
        )

    async def list_facts(self, *, owner_id: str, limit: int | None = None) -> list[MemoryFact]:
        return await asyncio.to_thread(self._list_facts_sync, owner_id, limit)

    def _list_facts_sync(self, owner_id: str, limit: int | None) -> list[MemoryFact]:
        effective_limit = limit or settings.memory_max_facts
        query = (
            self._facts_collection(owner_id)
            .order_by("createdAt", direction="DESCENDING")
            .limit(effective_limit)
        )
        facts: list[MemoryFact] = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            created_at = data.get("createdAt")
            facts.append(
                MemoryFact(
                    fact_id=doc.id,
                    owner_id=str(data.get("ownerId") or owner_id),
                    text=str(data.get("text") or ""),
                    category=str(data.get("category") or "general"),
                    created_at=created_at if isinstance(created_at, datetime) else datetime.now(timezone.utc),
                    session_id=data.get("sessionId") if isinstance(data.get("sessionId"), str) else None,
                )
            )
        return facts

    async def delete_fact(self, *, owner_id: str, fact_id: str) -> bool:
        return await asyncio.to_thread(self._delete_fact_sync, owner_id, fact_id)

    def _delete_fact_sync(self, owner_id: str, fact_id: str) -> bool:
        ref = self._facts_collection(owner_id).document(fact_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True


def format_memory_block(facts: list[MemoryFact], *, max_chars: int | None = None) -> str:
    """Render facts as a compact context block. Empty string when no facts."""
    budget = max_chars or settings.memory_injection_max_chars
    lines: list[str] = []
    used = 0
    for fact in facts:
        line = f"- ({fact.category}) {fact.text}"
        if used + len(line) + 1 > budget:
            break
        lines.append(line)
        used += len(line) + 1
    if not lines:
        return ""
    return "[USER MEMORY]\n" + "\n".join(lines) + "\n[END USER MEMORY]"


_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
