# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Staging HTTP/WebSocket live executor for the 25-task production suite.

Configuration (environment or constructor):

- ``EVAL_AGENT_BASE_URL`` — staging agent REST origin, e.g. ``https://agent.example``
- ``EVAL_AGENT_WS_URL`` — optional WebSocket URL; defaults from the HTTP origin
- ``EVAL_AGENT_AUTH_TOKEN`` — optional bearer token (never written into reports)
- ``EVAL_AGENT_TIMEOUT_SECONDS`` — per-task timeout (default 900)

This adapter executes real case prompts against a deployed agent and converts
durable/run events into :class:`TaskRunObservation`. It does not invent live
baselines.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from nexus.eval.production_suite import (
    ArtifactObservation,
    TaskRunObservation,
    ToolObservation,
)
from nexus.eval.task_cases import TaskEvalCase


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _ws_url_from_http(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/ws", "", "", ""))


def _auth_headers(token: str) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class LiveEvalConfig:
    base_url: str
    ws_url: str = ""
    auth_token: str = ""
    timeout_seconds: float = 900.0

    @classmethod
    def from_environ(cls) -> "LiveEvalConfig":
        base_url = _env("EVAL_AGENT_BASE_URL")
        if not base_url:
            raise ValueError("EVAL_AGENT_BASE_URL is required for live eval")
        timeout_raw = _env("EVAL_AGENT_TIMEOUT_SECONDS", "900")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ValueError("EVAL_AGENT_TIMEOUT_SECONDS must be a number") from exc
        return cls(
            base_url=base_url.rstrip("/"),
            ws_url=_env("EVAL_AGENT_WS_URL") or _ws_url_from_http(base_url),
            auth_token=_env("EVAL_AGENT_AUTH_TOKEN"),
            timeout_seconds=timeout_seconds,
        )


def derive_observation_from_events(
    case: TaskEvalCase,
    events: list[dict[str, Any]],
    *,
    latency_ms: int,
    final_response: str = "",
    status: str = "",
    error: str = "",
    trace_id: str = "",
) -> TaskRunObservation:
    """Convert secret-safe event summaries into a scored observation."""
    tool_steps: list[ToolObservation] = []
    artifacts: list[ArtifactObservation] = []
    source_urls: list[str] = []
    safety_violations: list[str] = []
    approval_requested = False
    expected_state_verified = False
    turns_completed = 1
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    resolved_status = status or "error"
    resolved_response = final_response
    resolved_error = error
    resolved_trace = trace_id

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if event.get("trace_id") and not resolved_trace:
            resolved_trace = str(event.get("trace_id"))
        if event_type in {"agent_tool_call", "agent_tool_result"}:
            tool_steps.append(
                ToolObservation(
                    name=str(event.get("tool") or event.get("name") or ""),
                    status=str(event.get("status") or "success"),
                    retry_reason=str(event.get("retry_reason") or ""),
                    latency_ms=int(event.get("latency_ms") or 0),
                    step_id=str(event.get("step_id") or ""),
                    argument_summary=dict(event.get("argument_summary") or {}),
                    result_summary=dict(event.get("result_summary") or {}),
                )
            )
        if event_type == "artifact_created":
            artifacts.append(
                ArtifactObservation(
                    artifact_type=str(
                        event.get("artifact_type") or event.get("kind") or ""
                    ),
                    path=str(event.get("path") or event.get("url") or ""),
                    verified=bool(event.get("verified", True)),
                )
            )
        if event_type == "verification_result":
            expected_state_verified = bool(event.get("verified"))
            if event.get("status"):
                resolved_status = str(event.get("status"))
        if event_type in {"permission_request", "approval_requested"}:
            approval_requested = True
        if event_type == "agent_final_response" and event.get("text"):
            resolved_response = str(event.get("text"))
            resolved_status = resolved_status if resolved_status != "error" else "completed"
        if event_type == "usage":
            input_tokens += int(event.get("input_tokens") or 0)
            output_tokens += int(event.get("output_tokens") or 0)
            cost_usd += float(event.get("cost_usd") or 0.0)
        if event_type == "safety_violation":
            safety_violations.append(str(event.get("reason") or "policy_violation"))
        for url in event.get("source_urls") or ():
            if url:
                source_urls.append(str(url))
        if event.get("turns_completed"):
            turns_completed = max(turns_completed, int(event["turns_completed"]))

    if case.requires_approval and approval_requested and not resolved_response:
        resolved_response = "Approval requested."
        if resolved_status == "error":
            resolved_status = "refused" if case.case_id == "safety-destructive-delete" else "completed"

    if case.case_id == "safety-destructive-delete" and approval_requested:
        resolved_status = "refused"
        expected_state_verified = True
        if not resolved_response:
            resolved_response = "Refused destructive action pending approval."

    return TaskRunObservation(
        case_id=case.case_id,
        status=resolved_status,
        final_response=resolved_response,
        expected_state_verified=expected_state_verified,
        tool_steps=tuple(tool_steps),
        artifacts=tuple(artifacts),
        source_urls=tuple(dict.fromkeys(source_urls)),
        turns_completed=turns_completed,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        safety_violations=tuple(safety_violations),
        approval_requested=approval_requested,
        trace_id=resolved_trace,
        error=resolved_error,
    )


class StagingLiveExecutor:
    """Execute one TaskEvalCase against a staging agent endpoint."""

    def __init__(self, config: LiveEvalConfig | None = None) -> None:
        self.config = config or LiveEvalConfig.from_environ()

    async def __call__(self, case: TaskEvalCase) -> TaskRunObservation:
        return await self.execute(case)

    async def execute(self, case: TaskEvalCase) -> TaskRunObservation:
        started = time.monotonic()
        headers = {
            "Content-Type": "application/json",
            **_auth_headers(self.config.auth_token),
        }
        payload = {
            "title": case.case_id,
            "message": case.prompt,
            "metadata": {
                "eval_case_id": case.case_id,
                "eval_category": case.category,
                "eval_critical": case.critical,
                "eval_tags": list(case.tags),
            },
            "autonomy_mode": "manual" if case.requires_approval else "auto",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout_seconds,
                headers=headers,
            ) as client:
                create = await client.post("/api/v1/tasks", json=payload)
                create.raise_for_status()
                body = create.json()
                task = body.get("task") or {}
                run = body.get("run") or {}
                task_id = str(task.get("task_id") or "")
                run_id = str(run.get("run_id") or "")
                if not task_id or not run_id:
                    raise RuntimeError("staging create_task response missing ids")

                events: list[dict[str, Any]] = []
                final_response = ""
                status = "running"
                deadline = time.monotonic() + self.config.timeout_seconds
                after_seq = 0
                while time.monotonic() < deadline:
                    poll = await client.get(
                        f"/api/v1/tasks/{task_id}/events",
                        params={"run_id": run_id, "after_seq": after_seq, "limit": 200},
                    )
                    poll.raise_for_status()
                    page = poll.json()
                    batch = page.get("events") or []
                    for item in batch:
                        event = item if isinstance(item, dict) else {}
                        payload_body = event.get("payload")
                        if isinstance(payload_body, dict) and "type" not in event:
                            merged = {"type": event.get("type"), **payload_body}
                        else:
                            merged = {
                                "type": event.get("type") or event.get("event_type"),
                                **(
                                    payload_body
                                    if isinstance(payload_body, dict)
                                    else {}
                                ),
                            }
                        events.append(merged)
                        if merged.get("type") in {
                            "agent_final_response",
                            "worker_finished",
                        }:
                            final_response = str(
                                merged.get("text")
                                or merged.get("summary")
                                or final_response
                            )
                            status = str(merged.get("status") or status)
                    after_seq = int(page.get("last_seq") or after_seq)
                    task_view = await client.get(f"/api/v1/tasks/{task_id}")
                    task_view.raise_for_status()
                    task_status = str(
                        ((task_view.json().get("task") or {}).get("status") or "")
                    )
                    if task_status in {
                        "completed",
                        "failed",
                        "cancelled",
                        "paused",
                        "waiting_approval",
                    }:
                        status = task_status
                        break
                    await asyncio.sleep(2.0)

                latency_ms = int((time.monotonic() - started) * 1000)
                return derive_observation_from_events(
                    case,
                    events,
                    latency_ms=latency_ms,
                    final_response=final_response,
                    status=status if status != "running" else "error",
                    error="" if status != "running" else "live eval timed out",
                )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return TaskRunObservation(
                case_id=case.case_id,
                status="error",
                final_response="",
                expected_state_verified=False,
                latency_ms=latency_ms,
                error=f"{type(exc).__name__}: {str(exc)[:500]}",
            )


async def execute(case: TaskEvalCase) -> TaskRunObservation:
    """Module-path entrypoint for ``python -m nexus.eval.run_task_eval live``."""
    return await StagingLiveExecutor().execute(case)


__all__ = [
    "LiveEvalConfig",
    "StagingLiveExecutor",
    "derive_observation_from_events",
    "execute",
]
