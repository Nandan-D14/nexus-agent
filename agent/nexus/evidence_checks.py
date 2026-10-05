# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Async, network-backed completion evidence checks.

``verify_completion`` stays pure and synchronous. Checks that need I/O run
here, only on the final (persisted) verification of a turn.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from nexus.config import settings
from nexus.control_loop import SUCCESS_STATUSES, ActionLedger, CompletionVerification
from nexus.net_safety import UnsafeUrlError, guarded_async_client

logger = logging.getLogger(__name__)

_PREVIEW_TOOLS = frozenset({"publish_app_preview"})
_MAX_PREVIEWS = 3


def _current_turn_preview_urls(ledger: ActionLedger) -> list[str]:
    urls: list[str] = []
    for record in ledger.records:
        observation = record.observation
        if (
            record.turn_index != ledger.current_turn_index
            or record.decision.action not in _PREVIEW_TOOLS
            or observation is None
            or observation.status not in SUCCESS_STATUSES
        ):
            continue
        for artifact in observation.artifacts:
            url = str(artifact.get("url") or artifact.get("preview_url") or "").strip()
            if url.startswith("https://") and url not in urls:
                urls.append(url)
    return urls[:_MAX_PREVIEWS]


async def _reachable(client: httpx.AsyncClient, url: str) -> bool:
    try:
        response = await client.get(url)
    except (httpx.HTTPError, UnsafeUrlError):
        return False
    # Auth walls still prove a server is answering; 5xx/404 mean a dead preview.
    return response.status_code < 400 or response.status_code in {401, 403}


async def check_preview_urls(ledger: ActionLedger) -> CompletionVerification | None:
    """Return a failed verification when a published preview does not answer."""
    if not settings.verify_preview_urls:
        return None
    urls = _current_turn_preview_urls(ledger)
    if not urls:
        return None
    timeout = float(settings.preview_check_timeout_seconds)
    try:
        async with guarded_async_client(follow_redirects=True, timeout=timeout) as client:
            results = await asyncio.gather(*(_reachable(client, url) for url in urls))
    except Exception:
        logger.debug("Preview reachability check skipped", exc_info=True)
        return None
    dead = [url for url, ok in zip(urls, results) if not ok]
    if not dead:
        return None
    return CompletionVerification(
        verified=False,
        status="failed",
        method="preview_http",
        summary="The published preview did not respond: " + ", ".join(dead),
        error_code="PREVIEW_UNREACHABLE",
        evidence=dead,
        remaining_work=[
            "Restart the dev server bound to 0.0.0.0 (background=True), confirm the "
            "port, then republish with publish_app_preview."
        ],
        retryable=True,
    )


__all__ = ["check_preview_urls"]
