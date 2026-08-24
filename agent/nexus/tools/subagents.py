# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Orchestrator tools for hidden background subagents."""

from __future__ import annotations

from nexus.config import settings
from nexus.tools._context import get_subagent_supervisor, get_task_id
from nexus.tools.base import normalized_tool, tool_error, tool_success


def _supervisor():
    supervisor = get_subagent_supervisor()
    if supervisor is None:
        raise RuntimeError("Subagent supervisor is not available in this session.")
    return supervisor


@normalized_tool
async def invoke_subagent(prompt: str, role: str = "worker", type_name: str = "general") -> dict:
    """Spawn a durable researcher, coder, or writer subagent."""
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        return tool_error("prompt is required.", error_code="INVALID_SUBAGENT_PROMPT")
    try:
        supervisor = _supervisor()
        if get_task_id().startswith("task_") and (
            not settings.durable_subagents_enabled
            or not supervisor.durable
        ):
            return tool_error(
                "Durable subagent persistence is unavailable; keep restart-sensitive work in the foreground task.",
                error_code="SUBAGENT_NOT_DURABLE",
                suggested_alternatives=[
                    "terminal_worker",
                    "desktop_worker",
                    "request_background_task",
                ],
            )
        record = await supervisor.spawn(
            prompt=clean_prompt,
            role=role,
            type_name=type_name,
        )
        return tool_success(
            f"Spawned subagent {record.subagent_id}.",
            **record.payload(),
        )
    except Exception as exc:
        return tool_error(str(exc), error_code="SUBAGENT_SPAWN_FAILED")


@normalized_tool
async def send_message(subagent_id: str, message: str) -> dict:
    """Queue a message for a hidden subagent and wake it if idle."""
    try:
        record = await _supervisor().send_message(subagent_id, message)
        return tool_success(
            f"Message queued for {record.subagent_id}.",
            **record.payload(),
        )
    except KeyError:
        return tool_error("Subagent not found.", error_code="SUBAGENT_NOT_FOUND")
    except Exception as exc:
        return tool_error(str(exc), error_code="SUBAGENT_MESSAGE_FAILED")


@normalized_tool
async def get_subagent_result(subagent_id: str) -> dict:
    """Return status/result for one hidden subagent."""
    try:
        record = await _supervisor().consume_result(subagent_id)
        return tool_success(
            f"Subagent {record.subagent_id} status: {record.status}.",
            **record.payload(),
        )
    except KeyError:
        return tool_error("Subagent not found.", error_code="SUBAGENT_NOT_FOUND")
    except Exception as exc:
        return tool_error(str(exc), error_code="SUBAGENT_RESULT_FAILED")


@normalized_tool
async def list_subagents() -> dict:
    """List hidden subagents for the current parent session."""
    try:
        records = [
            record.payload()
            for record in await _supervisor().consume_list()
        ]
        return tool_success(
            f"Listed {len(records)} subagent(s).",
            subagents=records,
            count=len(records),
        )
    except Exception as exc:
        return tool_error(str(exc), error_code="SUBAGENT_LIST_FAILED")


@normalized_tool
async def cancel_subagent(subagent_id: str) -> dict:
    """Cancel one hidden subagent."""
    try:
        record = await _supervisor().cancel(subagent_id)
        return tool_success(
            f"Cancelled subagent {record.subagent_id}.",
            **record.payload(),
        )
    except KeyError:
        return tool_error("Subagent not found.", error_code="SUBAGENT_NOT_FOUND")
    except Exception as exc:
        return tool_error(str(exc), error_code="SUBAGENT_CANCEL_FAILED")


@normalized_tool
async def await_subagents(subagent_ids: list[str] | None = None, timeout_seconds: int = 30) -> dict:
    """Wait briefly for hidden subagents before final synthesis."""
    try:
        records = await _supervisor().await_subagents(
            subagent_ids,
            timeout_seconds=max(0, int(timeout_seconds)),
        )
        return tool_success(
            f"Collected {len(records)} subagent status record(s).",
            subagents=records,
            count=len(records),
        )
    except KeyError:
        return tool_error("Subagent not found.", error_code="SUBAGENT_NOT_FOUND")
    except Exception as exc:
        return tool_error(str(exc), error_code="SUBAGENT_AWAIT_FAILED")
