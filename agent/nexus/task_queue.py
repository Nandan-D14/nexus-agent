# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Cloud Tasks enqueue helpers for durable task execution."""

from __future__ import annotations

import json
import logging
import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from nexus.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnqueueResult:
    queued: bool
    provider: str
    name: str = ""
    reason: str = ""


# Keep strong references to locally spawned worker tasks so the event loop
# does not garbage-collect them mid-run. Their lifetime is the server
# process, NOT the WebSocket connection — that is the whole point.
_local_worker_tasks: set[asyncio.Task] = set()


def local_worker_task_count() -> int:
    """Number of in-flight local durable worker tasks (for tests/observability)."""
    return sum(1 for task in _local_worker_tasks if not task.done())


async def _fail_unstarted_local_run(
    task_id: str,
    run_id: str,
    exc: BaseException,
) -> None:
    """Mark a run failed after the local worker task itself crashed.

    Best effort: this is the last line of defence against a run that produces
    no terminal event, so every failure here is swallowed and logged.
    """
    reason = str(exc) or exc.__class__.__name__
    try:
        from nexus.dependencies import get_production_task_repository

        repo = get_production_task_repository()
        task = await repo.get_task(task_id)
        if task is None:
            return
        run = await repo.get_run(
            task_id=task_id,
            run_id=run_id,
            owner_id=task.owner_id,
        )
        if run is not None and run.status in {"completed", "failed", "cancelled"}:
            return
        await repo.finish_run(
            task_id=task_id,
            run_id=run_id,
            status="failed",
            summary=reason[:1000],
            error=reason[:1000],
        )
        await repo.append_event(
            task_id=task_id,
            owner_id=task.owner_id,
            run_id=run_id,
            event_type="worker_failed",
            payload={"error": reason[:1000], "origin": "local_queue"},
        )
    except Exception:
        logger.exception(
            "Failed to mark crashed local run task=%s run=%s as failed",
            task_id,
            run_id,
        )


class TaskQueue:
    """Queue facade.

    Uses Cloud Tasks when configured. When the durable worker is enabled but
    Cloud Tasks is not configured, falls back to an in-process asyncio queue
    (``task_queue_local_fallback``) so runs still execute detached from the
    WebSocket and survive a browser close. With everything off it returns a
    no-op result so callers can still create durable task records.
    """

    def is_cloud_configured(self) -> bool:
        return bool(
            settings.gcp_tasks_project_id
            and settings.gcp_tasks_location
            and settings.gcp_tasks_queue
            and settings.gcp_tasks_worker_url
        )

    def is_configured(self) -> bool:
        return self.is_cloud_configured() or bool(
            settings.task_queue_local_fallback and not settings.is_production
        )

    async def enqueue_task_run(
        self,
        *,
        task_id: str,
        run_id: str,
        claim_token: str | None = None,
        delay_seconds: int = 0,
    ) -> EnqueueResult:
        if not settings.task_worker_enabled:
            return EnqueueResult(
                queued=False,
                provider="none",
                reason="Durable task worker is disabled.",
            )
        if not self.is_cloud_configured():
            if settings.task_queue_local_fallback and not settings.is_production:
                return self._enqueue_local(
                    task_id=task_id,
                    run_id=run_id,
                    claim_token=claim_token,
                    delay_seconds=delay_seconds,
                )
            return EnqueueResult(
                queued=False,
                provider="none",
                reason="Cloud Tasks is not configured.",
            )

        try:
            from google.cloud import tasks_v2
            from google.protobuf import duration_pb2, timestamp_pb2
            from google.api_core.exceptions import AlreadyExists
        except Exception as exc:
            logger.warning("Cloud Tasks client unavailable: %s", exc)
            return EnqueueResult(
                queued=False,
                provider="cloud_tasks",
                reason="google-cloud-tasks is not installed.",
            )

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(
            settings.gcp_tasks_project_id,
            settings.gcp_tasks_location,
            settings.gcp_tasks_queue,
        )
        payload: dict[str, Any] = {
            "task_id": task_id,
            "run_id": run_id,
            "claim_token": claim_token,
        }
        headers = {"Content-Type": "application/json"}
        if settings.task_worker_auth_token:
            headers["X-Worker-Token"] = settings.task_worker_auth_token

        task = {
            "name": client.task_path(
                settings.gcp_tasks_project_id,
                settings.gcp_tasks_location,
                settings.gcp_tasks_queue,
                re.sub(
                    r"[^A-Za-z0-9_-]",
                    "-",
                    f"{task_id}-{run_id}-{(claim_token or 'legacy')[-12:]}",
                )[:500],
            ),
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": settings.gcp_tasks_worker_url,
                "headers": headers,
                "body": json.dumps(payload).encode("utf-8"),
            }
        }
        dispatch_deadline = duration_pb2.Duration()
        dispatch_deadline.seconds = min(
            max(int(settings.task_worker_lease_seconds) + 60, 60),
            1800,
        )
        task["dispatch_deadline"] = dispatch_deadline
        if settings.gcp_tasks_oidc_service_account:
            task["http_request"]["oidc_token"] = {
                "service_account_email": settings.gcp_tasks_oidc_service_account,
            }
        if delay_seconds > 0:
            schedule_time = timestamp_pb2.Timestamp()
            schedule_time.FromDatetime(
                datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            )
            task["schedule_time"] = schedule_time

        try:
            created = await asyncio.to_thread(
                client.create_task,
                request={"parent": parent, "task": task},
            )
            return EnqueueResult(
                queued=True,
                provider="cloud_tasks",
                name=created.name,
            )
        except AlreadyExists:
            return EnqueueResult(
                queued=True,
                provider="cloud_tasks",
                name=str(task["name"]),
                reason="Task dispatch already exists.",
            )
        except Exception as exc:
            logger.exception(
                "Failed to enqueue Cloud Task for %s/%s",
                task_id,
                run_id,
            )
            return EnqueueResult(
                queued=False,
                provider="cloud_tasks",
                name=str(task["name"]),
                reason=str(exc)[:500],
            )

    def _enqueue_local(
        self,
        *,
        task_id: str,
        run_id: str,
        claim_token: str | None = None,
        delay_seconds: int = 0,
    ) -> EnqueueResult:
        """Run the durable worker in-process, detached from the caller.

        The spawned asyncio task lives on the server event loop, so it keeps
        executing after the WebSocket handler that enqueued it returns
        (browser closed, tab navigated away, network drop).
        """

        async def _run() -> None:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            # Imported lazily: task_worker -> dependencies -> task_queue would
            # otherwise be a circular import at module load time.
            from nexus.task_worker import task_worker

            try:
                kwargs = {"task_id": task_id, "run_id": run_id}
                if claim_token:
                    kwargs["claim_token"] = claim_token
                result = await task_worker.run_once(**kwargs)
                logger.info(
                    "Local durable worker finished task=%s run=%s status=%s",
                    task_id,
                    run_id,
                    result.status,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "Local durable worker crashed for task=%s run=%s", task_id, run_id
                )
                # Nothing else owns this run: the crash happened outside the
                # worker's own recovery path, so without a terminal event the
                # client waits on a run that will never emit anything again.
                await _fail_unstarted_local_run(task_id, run_id, exc)

        worker_task = asyncio.get_running_loop().create_task(
            _run(), name=f"local-durable-{task_id}-{run_id}"
        )
        _local_worker_tasks.add(worker_task)
        worker_task.add_done_callback(_local_worker_tasks.discard)
        return EnqueueResult(
            queued=True,
            provider="local",
            name=f"{task_id}/{run_id}",
        )


task_queue = TaskQueue()
