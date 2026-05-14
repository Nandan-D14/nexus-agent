# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Cloud Tasks enqueue helpers for durable task execution."""

from __future__ import annotations

import json
import logging
import asyncio
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


class TaskQueue:
    """Queue facade.

    Uses Cloud Tasks when configured. In local/dev it returns a no-op result so
    callers can still create durable tasks without requiring GCP credentials.
    """

    def is_configured(self) -> bool:
        return bool(
            settings.gcp_tasks_project_id
            and settings.gcp_tasks_location
            and settings.gcp_tasks_queue
            and settings.gcp_tasks_worker_url
        )

    async def enqueue_task_run(
        self,
        *,
        task_id: str,
        run_id: str,
        delay_seconds: int = 0,
    ) -> EnqueueResult:
        if not settings.task_worker_enabled:
            return EnqueueResult(
                queued=False,
                provider="none",
                reason="Durable task worker is disabled.",
            )
        if not self.is_configured():
            return EnqueueResult(
                queued=False,
                provider="none",
                reason="Cloud Tasks is not configured.",
            )

        try:
            from google.cloud import tasks_v2
            from google.protobuf import timestamp_pb2
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
        payload: dict[str, Any] = {"task_id": task_id, "run_id": run_id}
        headers = {"Content-Type": "application/json"}
        if settings.task_worker_auth_token:
            headers["X-Worker-Token"] = settings.task_worker_auth_token

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": settings.gcp_tasks_worker_url,
                "headers": headers,
                "body": json.dumps(payload).encode("utf-8"),
            }
        }
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

        created = await asyncio.to_thread(
            client.create_task,
            request={"parent": parent, "task": task},
        )
        return EnqueueResult(queued=True, provider="cloud_tasks", name=created.name)


task_queue = TaskQueue()
