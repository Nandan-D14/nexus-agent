# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import asyncio
import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.runtime_config import SessionRuntimeConfig
from nexus.subagent_store import FirestoreSubagentRepository
from nexus.subagents import SubagentSupervisor


class _Snapshot:
    def __init__(self, doc_id: str, data: dict | None) -> None:
        self.id = doc_id
        self.exists = data is not None
        self._data = copy.deepcopy(data)

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data or {})


class _Document:
    def __init__(self, db: "_Firestore", collection: str, doc_id: str) -> None:
        self._db = db
        self._key = (collection, doc_id)
        self.id = doc_id

    def get(self, transaction=None) -> _Snapshot:
        del transaction
        return _Snapshot(self.id, self._db.data.get(self._key))

    def set(self, values: dict, merge: bool = False) -> None:
        if merge:
            current = copy.deepcopy(self._db.data.get(self._key) or {})
            current.update(copy.deepcopy(values))
            self._db.data[self._key] = current
        else:
            self._db.data[self._key] = copy.deepcopy(values)


class _Collection:
    def __init__(self, db: "_Firestore", name: str) -> None:
        self._db = db
        self._name = name

    def document(self, doc_id: str) -> _Document:
        return _Document(self._db, self._name, doc_id)

    def where(self, **_kwargs) -> "_Collection":
        return self

    def stream(self):
        for (collection, doc_id), data in list(self._db.data.items()):
            if collection == self._name:
                yield _Snapshot(doc_id, data)


class _Transaction:
    def set(self, ref: _Document, values: dict, merge: bool = False) -> None:
        ref.set(values, merge=merge)


class _Firestore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict] = {}

    def collection(self, name: str) -> _Collection:
        return _Collection(self, name)

    def transaction(self) -> _Transaction:
        return _Transaction()


class _History:
    def __init__(self) -> None:
        self.completed = 0
        self.failed = 0

    async def complete_step(self, **_kwargs):
        self.completed += 1
        return None

    async def fail_step(self, **_kwargs):
        self.failed += 1
        return None


def _runtime_config() -> SessionRuntimeConfig:
    return SessionRuntimeConfig(
        e2b_api_key="test-e2b",
        gemini_provider="apiKey",
        gemini_api_key="test-gemini",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model="gemini-test",
        gemini_agent_fallback_models=(),
        gemini_light_model="gemini-light-test",
        gemini_live_model="gemini-live-test",
        gemini_live_region="us-central1",
        gemini_vision_model="gemini-vision-test",
        gemini_vision_fallback_models=("gemini-vision-fallback",),
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
    )


def _turn_result(text: str):
    return SimpleNamespace(response=text, usage_records=[], error=None)


def _supervisor(
    repository: FirestoreSubagentRepository,
    *,
    history=None,
) -> SubagentSupervisor:
    return SubagentSupervisor(
        runtime_config=_runtime_config(),
        session_service=object(),
        owner_id="user-1",
        parent_session_id="session-1",
        parent_run_id="run-1",
        parent_task_id="task-1",
        history_repository=history,
        subagent_repository=repository,
    )


def _payload(subagent_id: str, *, step_id: str | None = None) -> dict:
    return {
        "subagentId": subagent_id,
        "hiddenSessionId": f"hidden-{subagent_id}",
        "parentSessionId": "session-1",
        "parentRunId": "run-1",
        "parentTaskId": "task-1",
        "ownerId": "user-1",
        "role": "researcher",
        "typeName": "researcher",
        "prompt": "Find the answer",
        "stepId": step_id,
    }


class DurableSubagentTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.transactional = patch(
            "nexus.subagent_store.firestore.transactional",
            side_effect=lambda function: function,
        )
        self.transactional.start()
        self.addCleanup(self.transactional.stop)
        self.db = _Firestore()
        self.repository = FirestoreSubagentRepository(db=self.db)

    async def test_claim_lease_prevents_duplicate_execution(self) -> None:
        await self.repository.create_record(_payload("subagent-lease"))
        first = await self.repository.claim(
            subagent_id="subagent-lease",
            owner_id="user-1",
            worker_id="worker-a",
        )
        duplicate = await self.repository.claim(
            subagent_id="subagent-lease",
            owner_id="user-1",
            worker_id="worker-b",
        )

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertEqual(first["claimGeneration"], 1)

        self.db.collection("subagent_records").document(
            "subagent-lease"
        ).set(
            {
                "leaseExpiresAt": datetime.now(timezone.utc)
                - timedelta(seconds=1)
            },
            merge=True,
        )
        reclaimed = await self.repository.claim(
            subagent_id="subagent-lease",
            owner_id="user-1",
            worker_id="worker-b",
        )
        self.assertEqual(reclaimed["claimGeneration"], 2)
        self.assertEqual(reclaimed["leaseOwner"], "worker-b")

    async def test_restart_recovers_mailbox_checkpoint_and_result(self) -> None:
        first_started = asyncio.Event()
        never_release = asyncio.Event()
        first = _supervisor(self.repository)

        async def interrupted_turn(_record, _message):
            first_started.set()
            await never_release.wait()
            return _turn_result("stale result")

        first._run_turn = AsyncMock(side_effect=interrupted_turn)  # type: ignore[method-assign]
        first_record = await first.spawn(
            prompt="durable work",
            role="researcher",
            type_name="researcher",
        )
        await asyncio.wait_for(first_started.wait(), timeout=1)

        self.db.collection("subagent_records").document(
            first_record.subagent_id
        ).set(
            {
                "leaseExpiresAt": datetime.now(timezone.utc)
                - timedelta(seconds=1)
            },
            merge=True,
        )

        second = _supervisor(self.repository)
        second._run_turn = AsyncMock(  # type: ignore[method-assign]
            return_value=_turn_result("recovered result")
        )
        recovered = await second.recover_for_run()
        self.assertEqual(len(recovered), 1)
        await asyncio.wait_for(recovered[0].task, timeout=1)

        first_record.task.cancel()
        await asyncio.gather(first_record.task, return_exceptions=True)

        stored = await self.repository.get_record(
            subagent_id=first_record.subagent_id,
            owner_id="user-1",
        )
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["result"], "recovered result")
        self.assertEqual(stored["claimGeneration"], 2)
        self.assertTrue(stored["terminalRecorded"])
        self.assertFalse(stored["resultConsumed"])
        self.assertEqual(stored["checkpoint"]["turnCount"], 1)
        self.assertEqual(
            stored["checkpoint"]["lastResult"],
            "recovered result",
        )
        self.assertEqual(second._run_turn.await_count, 1)

        await second.consume_result(first_record.subagent_id)
        consumed = await self.repository.get_record(
            subagent_id=first_record.subagent_id,
            owner_id="user-1",
        )
        self.assertTrue(consumed["resultConsumed"])

    async def test_cancel_survives_restart_without_reexecution(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        first = _supervisor(self.repository)

        async def blocked(_record, _message):
            started.set()
            await release.wait()
            return _turn_result("too late")

        first._run_turn = AsyncMock(side_effect=blocked)  # type: ignore[method-assign]
        record = await first.spawn(
            prompt="cancel me",
            role="coder",
            type_name="coder",
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        await first.cancel(record.subagent_id)

        second = _supervisor(self.repository)
        second._run_turn = AsyncMock()  # type: ignore[method-assign]
        recovered = await second.recover_for_run()
        stored = await self.repository.get_record(
            subagent_id=record.subagent_id,
            owner_id="user-1",
        )

        self.assertEqual(recovered[0].status, "cancelled")
        self.assertEqual(stored["status"], "cancelled")
        self.assertTrue(stored["terminalRecorded"])
        second._run_turn.assert_not_awaited()

    async def test_terminal_parent_step_reconciles_exactly_once(self) -> None:
        await self.repository.create_record(
            _payload("subagent-terminal", step_id="step-1")
        )
        claim = await self.repository.claim(
            subagent_id="subagent-terminal",
            owner_id="user-1",
            worker_id="dead-worker",
        )
        message = await self.repository.claim_next_message(
            subagent_id="subagent-terminal",
            owner_id="user-1",
            worker_id="dead-worker",
            claim_generation=claim["claimGeneration"],
        )
        await self.repository.complete_message(
            subagent_id="subagent-terminal",
            owner_id="user-1",
            worker_id="dead-worker",
            claim_generation=claim["claimGeneration"],
            message_id=message["messageId"],
            result="persisted answer",
        )
        await self.repository.mark_terminal(
            subagent_id="subagent-terminal",
            owner_id="user-1",
            status="completed",
            result="persisted answer",
            error=None,
            terminal_recorded=False,
            worker_id="dead-worker",
            claim_generation=claim["claimGeneration"],
        )

        history = _History()
        await _supervisor(
            self.repository,
            history=history,
        ).recover_for_run()
        await _supervisor(
            self.repository,
            history=history,
        ).recover_for_run()

        self.assertEqual(history.completed, 1)
        stored = await self.repository.get_record(
            subagent_id="subagent-terminal",
            owner_id="user-1",
        )
        self.assertTrue(stored["terminalRecorded"])

    async def test_only_existing_subagent_surfaces_are_accepted(self) -> None:
        supervisor = _supervisor(self.repository)
        with self.assertRaisesRegex(ValueError, "researcher, coder, or writer"):
            await supervisor.spawn(
                prompt="work",
                role="new persona",
                type_name="executor",
            )

