# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Hidden background subagent supervisor."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from google.adk.agents import Agent

from nexus.runtime_config import SessionRuntimeConfig
from nexus.config import settings
from nexus.subagent_store import TERMINAL_SUBAGENT_STATUSES
from nexus.subagent_resources import ToolResourceLocks
from nexus.tool_gateway import gate_tools
from nexus.usage import TokenUsageRecord

logger = logging.getLogger(__name__)

UsageCallback = Callable[[TokenUsageRecord], Awaitable[None]]
SendJsonCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class SubagentRecord:
    subagent_id: str
    hidden_session_id: str
    parent_session_id: str
    parent_run_id: str | None
    parent_task_id: str | None
    owner_id: str
    role: str
    type_name: str
    prompt: str
    status: str = "queued"
    result: str | None = None
    error: str | None = None
    step_id: str | None = None
    terminal_recorded: bool = False
    result_consumed: bool = False
    claim_generation: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    checkpoint: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task: asyncio.Task | None = field(default=None, repr=False)
    mailbox: asyncio.Queue[str] = field(default_factory=asyncio.Queue, repr=False)

    def payload(self) -> dict[str, Any]:
        return {
            "subagent_id": self.subagent_id,
            "hidden_session_id": self.hidden_session_id,
            "parent_session_id": self.parent_session_id,
            "parent_run_id": self.parent_run_id,
            "parent_task_id": self.parent_task_id,
            "role": self.role,
            "type_name": self.type_name,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "step_id": self.step_id,
            "terminal_recorded": self.terminal_recorded,
            "result_consumed": self.result_consumed,
            "claim_generation": self.claim_generation,
            "lease_owner": self.lease_owner,
            "lease_expires_at": (
                self.lease_expires_at.isoformat()
                if self.lease_expires_at
                else None
            ),
            "checkpoint": self.checkpoint,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SubagentSupervisor:
    """Owns hidden background ADK runners for one parent session."""

    def __init__(
        self,
        *,
        runtime_config: SessionRuntimeConfig,
        session_service,
        owner_id: str,
        parent_session_id: str,
        parent_run_id: str | None,
        parent_task_id: str | None = None,
        history_repository=None,
        subagent_repository=None,
        send_json: SendJsonCallback | None = None,
        usage_callback: UsageCallback | None = None,
        resource_locks: ToolResourceLocks | None = None,
    ) -> None:
        self.runtime_config = runtime_config
        self.session_service = session_service
        self.owner_id = owner_id
        self.parent_session_id = parent_session_id
        self.parent_run_id = parent_run_id
        self.parent_task_id = parent_task_id
        self.history_repository = history_repository
        self.subagent_repository = subagent_repository
        self.send_json = send_json
        self.usage_callback = usage_callback
        self.resource_locks = resource_locks or ToolResourceLocks()
        self.worker_id = (
            f"{socket.gethostname()}-subagent-{uuid.uuid4().hex[:8]}"
        )
        self._records: dict[str, SubagentRecord] = {}
        from nexus.subagent_components import SubagentEventEmitter, SubagentStoreCodec

        self._codec = SubagentStoreCodec()
        self._emitter = SubagentEventEmitter(self)
        self._delegates = (self._codec, self._emitter)

    def __getattr__(self, name: str):
        # Only invoked for methods moved to the codec/emitter collaborators.
        # Class-level lookup avoids triggering the emitter's own __getattr__.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        for delegate in self.__dict__.get("_delegates", ()):
            if getattr(type(delegate), name, None) is not None:
                return getattr(delegate, name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    @property
    def durable(self) -> bool:
        return self.subagent_repository is not None

    async def spawn(self, *, prompt: str, role: str, type_name: str) -> SubagentRecord:
        subagent_id = f"sub_{uuid.uuid4().hex[:10]}"
        record = SubagentRecord(
            subagent_id=subagent_id,
            hidden_session_id=f"{self.parent_session_id}:sub:{subagent_id}",
            parent_session_id=self.parent_session_id,
            parent_run_id=self.parent_run_id,
            parent_task_id=self.parent_task_id,
            owner_id=self.owner_id,
            role=(role or "worker").strip()[:80],
            type_name=self._canonical_type(type_name),
            prompt=prompt.strip(),
        )
        if self.subagent_repository is not None:
            await self.subagent_repository.create_record(
                self._storage_payload(record)
            )
        self._records[subagent_id] = record
        await self._mark_started(record)
        await self._start_task(
            record,
            None if self.subagent_repository is not None else record.prompt,
        )
        return record

    async def send_message(self, subagent_id: str, message: str) -> SubagentRecord:
        record = self._require_record(subagent_id)
        clean = message.strip()
        if not clean:
            raise ValueError("message is required")
        if self.subagent_repository is not None:
            await self.subagent_repository.append_message(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
                text=clean,
            )
        else:
            await record.mailbox.put(clean)
        record.updated_at = datetime.now(timezone.utc)
        if record.task is None or record.task.done():
            await self._start_task(record, None)
        else:
            task = record.task

            def _restart_if_mailbox_pending(_task: asyncio.Task) -> None:
                if record.task is not _task:
                    return
                if record.status in {"cancelled", "failed"}:
                    return
                if self.subagent_repository is None and record.mailbox.empty():
                    return
                asyncio.create_task(self._start_task(record, None))

            task.add_done_callback(_restart_if_mailbox_pending)
        await self._record_progress(record, f"Queued message for {record.role}.")
        return record

    async def await_subagents(
        self,
        subagent_ids: list[str] | None = None,
        *,
        timeout_seconds: float = 30.0,
    ) -> list[dict[str, Any]]:
        records = self._select_records(subagent_ids)
        tasks = [record.task for record in records if record.task is not None and not record.task.done()]
        if tasks:
            try:
                await asyncio.wait(tasks, timeout=max(0.0, timeout_seconds))
            except asyncio.CancelledError:
                raise
        for record in records:
            if record.status == "completed":
                await self.consume_result(record.subagent_id)
        return [record.payload() for record in records]

    async def cancel(self, subagent_id: str) -> SubagentRecord:
        record = self._require_record(subagent_id)
        if record.status in TERMINAL_SUBAGENT_STATUSES:
            return record
        if record.task is not None and not record.task.done():
            record.task.cancel()
            await asyncio.gather(record.task, return_exceptions=True)
            if record.status == "cancelled":
                return record
        record.status = "cancelled"
        record.error = "Cancelled by orchestrator."
        record.updated_at = datetime.now(timezone.utc)
        await self._persist_terminal(
            record,
            terminal_recorded=False,
            force=True,
        )
        await self._mark_failed(record, status="cancelled")
        return record

    def get(self, subagent_id: str) -> SubagentRecord:
        return self._require_record(subagent_id)

    async def consume_result(self, subagent_id: str) -> SubagentRecord:
        record = self._require_record(subagent_id)
        if self.subagent_repository is not None:
            stored = await self.subagent_repository.get_record(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
            )
            if stored:
                self._apply_storage_record(record, stored)
        if record.status == "completed" and not record.result_consumed:
            record.result_consumed = True
            if self.subagent_repository is not None:
                await self.subagent_repository.update_record(
                    subagent_id=record.subagent_id,
                    owner_id=record.owner_id,
                    updates={"resultConsumed": True},
                )
        return record

    async def consume_list(self) -> list[SubagentRecord]:
        for record in self.list():
            if record.status == "completed" and not record.result_consumed:
                await self.consume_result(record.subagent_id)
        return self.list()

    def list(self) -> list[SubagentRecord]:
        return list(self._records.values())

    def update_parent_run(self, run_id: str | None) -> None:
        self.parent_run_id = run_id
        for record in self._records.values():
            record.parent_run_id = run_id
            record.updated_at = datetime.now(timezone.utc)
            if self.subagent_repository is not None:
                asyncio.create_task(
                    self.subagent_repository.update_record(
                        subagent_id=record.subagent_id,
                        owner_id=record.owner_id,
                        updates={"parentRunId": run_id},
                    )
                )

    def update_parent_task(self, task_id: str | None) -> None:
        self.parent_task_id = task_id
        for record in self._records.values():
            record.parent_task_id = task_id
            if self.subagent_repository is not None:
                asyncio.create_task(
                    self.subagent_repository.update_record(
                        subagent_id=record.subagent_id,
                        owner_id=record.owner_id,
                        updates={"parentTaskId": task_id},
                    )
                )

    async def _start_task(
        self,
        record: SubagentRecord,
        initial_message: str | None,
    ) -> bool:
        if record.task is not None and not record.task.done():
            return False
        if self.subagent_repository is not None:
            claimed = await self.subagent_repository.claim(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
                worker_id=self.worker_id,
            )
            if claimed is None:
                return False
            self._apply_storage_record(record, claimed)
        ctx = contextvars.copy_context()
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc)
        record.task = asyncio.create_task(
            self._run_loop(record, initial_message),
            context=ctx,
            name=f"subagent-{record.subagent_id}",
        )
        return True

    async def _run_loop(self, record: SubagentRecord, initial_message: str | None) -> None:
        heartbeat: asyncio.Task | None = None
        if self.subagent_repository is not None:
            heartbeat = asyncio.create_task(
                self._lease_heartbeat(record),
                name=f"subagent-heartbeat-{record.subagent_id}",
            )
        try:
            next_message = initial_message
            while True:
                message_id: str | None = None
                if self.subagent_repository is not None:
                    persistent_message = (
                        await self.subagent_repository.claim_next_message(
                            subagent_id=record.subagent_id,
                            owner_id=record.owner_id,
                            worker_id=self.worker_id,
                            claim_generation=record.claim_generation,
                        )
                    )
                    if persistent_message is None:
                        break
                    next_message = str(
                        persistent_message.get("text") or ""
                    )
                    message_id = str(
                        persistent_message.get("messageId") or ""
                    )
                elif next_message is None:
                    if record.mailbox.empty():
                        break
                    next_message = await record.mailbox.get()

                turn_task = asyncio.create_task(
                    self._run_turn(record, next_message)
                )
                if heartbeat is not None:
                    done, _ = await asyncio.wait(
                        {turn_task, heartbeat},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if heartbeat in done:
                        turn_task.cancel()
                        await asyncio.gather(
                            turn_task,
                            return_exceptions=True,
                        )
                        heartbeat_error = heartbeat.exception()
                        raise heartbeat_error or RuntimeError(
                            "Subagent lease heartbeat stopped."
                        )
                result = await turn_task
                if result.response:
                    record.result = result.response
                for usage in result.usage_records:
                    if self.usage_callback is not None:
                        await self.usage_callback(usage)
                if result.error:
                    raise RuntimeError(result.error)
                if (
                    self.subagent_repository is not None
                    and message_id
                ):
                    completed = (
                        await self.subagent_repository.complete_message(
                            subagent_id=record.subagent_id,
                            owner_id=record.owner_id,
                            worker_id=self.worker_id,
                            claim_generation=record.claim_generation,
                            message_id=message_id,
                            result=record.result,
                        )
                    )
                    if not completed:
                        raise RuntimeError(
                            "Subagent lost its mailbox checkpoint lease."
                        )
                    stored = await self.subagent_repository.get_record(
                        subagent_id=record.subagent_id,
                        owner_id=record.owner_id,
                    )
                    if stored:
                        self._apply_storage_record(record, stored)
                next_message = None
            record.status = "completed"
            record.updated_at = datetime.now(timezone.utc)
            await self._persist_terminal(record, terminal_recorded=False)
            await self._mark_completed(record)
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.error = "Cancelled."
            record.updated_at = datetime.now(timezone.utc)
            await self._persist_terminal(record, terminal_recorded=False)
            await self._mark_failed(record, status="cancelled")
        except Exception as exc:
            logger.exception("Subagent %s failed", record.subagent_id)
            record.status = "failed"
            record.error = str(exc) or "Subagent failed."
            record.updated_at = datetime.now(timezone.utc)
            await self._persist_terminal(record, terminal_recorded=False)
            await self._mark_failed(record)
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    async def _lease_heartbeat(self, record: SubagentRecord) -> None:
        interval = max(
            1,
            min(
                int(settings.subagent_heartbeat_interval_seconds),
                max(1, int(settings.subagent_lease_seconds) // 2),
            ),
        )
        while True:
            await asyncio.sleep(interval)
            renewed = await self.subagent_repository.renew_lease(
                subagent_id=record.subagent_id,
                owner_id=record.owner_id,
                worker_id=self.worker_id,
                claim_generation=record.claim_generation,
            )
            if not renewed:
                raise RuntimeError("Subagent lost its durable lease.")

    async def recover_for_run(self) -> list[SubagentRecord]:
        """Reload, reconcile, and reclaim eligible records after restart."""
        if self.subagent_repository is None or not self.parent_run_id:
            return []
        stored_records = await self.subagent_repository.list_for_parent(
            parent_session_id=self.parent_session_id,
            parent_run_id=self.parent_run_id,
            owner_id=self.owner_id,
        )
        recovered: list[SubagentRecord] = []
        for stored in stored_records:
            subagent_id = str(stored.get("subagentId") or "")
            if not subagent_id:
                continue
            record = self._records.get(subagent_id)
            if record is None:
                record = self._record_from_storage(stored)
                self._records[subagent_id] = record
            else:
                self._apply_storage_record(record, stored)
            recovered.append(record)
            if record.status in TERMINAL_SUBAGENT_STATUSES:
                if not record.terminal_recorded:
                    if record.status == "completed":
                        await self._mark_completed(record)
                    else:
                        await self._mark_failed(
                            record,
                            status=(
                                "cancelled"
                                if record.status == "cancelled"
                                else "failed"
                            ),
                        )
                continue
            await self._start_task(record, None)
        return recovered

    def checkpoint_snapshot(self) -> dict[str, Any]:
        """Return bounded parent-checkpoint linkage, not mailbox contents."""
        return {
            record.subagent_id: {
                "status": record.status,
                "result": (record.result or "")[:1000],
                "error": (record.error or "")[:500],
                "result_consumed": record.result_consumed,
                "claim_generation": record.claim_generation,
                "checkpoint": record.checkpoint,
            }
            for record in self._records.values()
        }

    async def _persist_terminal(
        self,
        record: SubagentRecord,
        *,
        terminal_recorded: bool,
        force: bool = False,
    ) -> None:
        if self.subagent_repository is None:
            return
        persisted = await self.subagent_repository.mark_terminal(
            subagent_id=record.subagent_id,
            owner_id=record.owner_id,
            status=record.status,
            result=record.result,
            error=record.error,
            terminal_recorded=terminal_recorded,
            worker_id=(
                self.worker_id
                if record.claim_generation > 0 and not force
                else None
            ),
            claim_generation=(
                record.claim_generation
                if record.claim_generation > 0 and not force
                else None
            ),
        )
        if not persisted:
            raise RuntimeError(
                f"Lost durable subagent claim for {record.subagent_id}"
            )

    async def _run_turn(self, record: SubagentRecord, message: str):
        from nexus.agent import create_runner, run_agent_turn

        agent = self._create_agent(record)
        runner, _ = create_runner(agent, session_service=self.session_service)
        return await run_agent_turn(
            runner=runner,
            session_service=self.session_service,
            session_id=record.hidden_session_id,
            user_id=record.owner_id,
            message=message,
            runtime_config=self.runtime_config,
        )

    def _create_agent(self, record: SubagentRecord) -> Agent:
        from nexus.model_select import create_model

        instruction = (
            "You are a hidden CoComputer background subagent. "
            "Do assigned work independently, keep output concise, and finish with a clear result. "
            "You are internal: do not ask the user questions. "
            "Use available tools when needed; shared sandbox and workspace mutations are locked. "
            f"Role: {record.role}. Type: {record.type_name}. "
            f"Parent session: {record.parent_session_id}. Parent run: {record.parent_run_id or 'none'}."
        )
        return Agent(
            name=f"background_{record.subagent_id}",
            model=create_model("micro", self.runtime_config),
            instruction=instruction,
            tools=gate_tools(self._tools_for_type(record.type_name)),
        )

    def _tools_for_type(self, type_name: str) -> list:
        """Typed tool surfaces for background micro-agents.

        Canonical types: researcher | coder | writer. Substring matching keeps
        older loose names ("web research", "shell helper") working.
        """
        from nexus.tools.bash import run_command
        from nexus.tools.docs import publish_html_artifact
        from nexus.tools.integrations import tavily_search
        from nexus.tools.retrieval import search_sources
        from nexus.tools.skills import read_skill, read_skill_file
        from nexus.tools.web import scrape_web_page, web_search
        from nexus.tools.workspace import (
            list_workspace_files,
            read_task_state,
            read_workspace_file,
            write_workspace_file,
        )

        lowered = type_name.lower()
        tools = [read_skill, read_skill_file, read_task_state, read_workspace_file, list_workspace_files]
        if any(part in lowered for part in ("research", "browser", "web", "search")):
            tools.extend([web_search, scrape_web_page, tavily_search, search_sources, write_workspace_file])
        if any(part in lowered for part in ("code", "terminal", "shell")):
            tools.append(run_command)
        if any(part in lowered for part in ("code", "writer", "general")):
            tools.extend([write_workspace_file, publish_html_artifact])
        # De-duplicate while preserving order (types can match several branches).
        seen: set[int] = set()
        deduped: list = []
        for tool in tools:
            if id(tool) not in seen:
                seen.add(id(tool))
                deduped.append(tool)
        return deduped

    def _select_records(self, subagent_ids: list[str] | None) -> list[SubagentRecord]:
        if not subagent_ids:
            return self.list()
        return [self._require_record(subagent_id) for subagent_id in subagent_ids]

    def _require_record(self, subagent_id: str) -> SubagentRecord:
        record = self._records.get(str(subagent_id or "").strip())
        if record is None:
            raise KeyError(f"Unknown subagent {subagent_id}")
        return record
