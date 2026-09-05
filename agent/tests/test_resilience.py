# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Bounded retries must give up so a turn can continue.

An operation that retries forever, or blocks with no deadline, is
indistinguishable from a hung agent. These tests pin the give-up behaviour.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nexus.resilience import (
    DeadlineExceeded,
    call_with_deadline,
    is_remote_deadline_error,
    retry_async,
    retry_sync,
)
from nexus.vision_provider import QwenVisionProvider, VisionAnalysisError


_GROUNDING_JSON = (
    '{"visible_state":"Desktop","focus":"","targets":[],'
    '"visible_text":[],"errors":[],"next_action":"","confidence":0.5}'
)


def test_retry_sync_succeeds_after_transient_failures() -> None:
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    assert retry_sync(flaky, attempts=3, base_delay=0, label="flaky") == "ok"
    assert len(calls) == 3


def test_retry_sync_gives_up_and_reraises() -> None:
    calls: list[int] = []

    def always_fails() -> None:
        calls.append(1)
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError, match="permanent"):
        retry_sync(always_fails, attempts=4, base_delay=0, label="always")

    # Bounded: exactly `attempts` calls, never an unbounded loop.
    assert len(calls) == 4


def test_retry_sync_skips_retry_for_give_up_errors() -> None:
    calls: list[int] = []

    class Fatal(Exception):
        pass

    def fatal() -> None:
        calls.append(1)
        raise Fatal("do not retry")

    with pytest.raises(Fatal):
        retry_sync(
            fatal,
            attempts=5,
            base_delay=0,
            give_up_on=(Fatal,),
            label="fatal",
        )

    assert len(calls) == 1


def test_call_with_deadline_bounds_a_blocking_call() -> None:
    started = time.monotonic()

    with pytest.raises(DeadlineExceeded):
        call_with_deadline(lambda: time.sleep(5), timeout=0.2, label="sleeper")

    # The caller is released at the deadline rather than waiting the full sleep.
    assert time.monotonic() - started < 2.0


@pytest.mark.asyncio
async def test_retry_async_gives_up_after_attempts() -> None:
    calls: list[int] = []

    async def always_fails() -> None:
        calls.append(1)
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await retry_async(always_fails, attempts=3, base_delay=0, label="async")

    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_async_applies_per_attempt_timeout() -> None:
    async def stalls() -> None:
        await asyncio.sleep(10)

    with pytest.raises(asyncio.TimeoutError):
        await retry_async(
            stalls,
            attempts=2,
            base_delay=0,
            timeout=0.05,
            retry_on=(asyncio.TimeoutError,),
            label="stall",
        )


def test_vision_retries_each_model_then_falls_back() -> None:
    """Every tier is retried, and exhaustion raises instead of hanging."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("upstream 503")

    with patch("nexus.vision_provider.OpenAI", return_value=fake_client):
        provider = QwenVisionProvider(
            api_key="test",
            api_base="https://qwen.example/v1",
            primary_model="qwen-vl",
            fallback_models=("qwen-vl-lite",),
            attempts_per_model=3,
            retry_base_seconds=0,
        )
        with pytest.raises(VisionAnalysisError, match="All vision models failed"):
            provider.analyze(b"jpeg", width=800, height=600)

    # 2 models x 3 attempts, then give up — a bounded, predictable ceiling.
    assert fake_client.chat.completions.create.call_count == 6


def test_vision_recovers_on_a_later_attempt() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=_GROUNDING_JSON))]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        RuntimeError("transient"),
        response,
    ]

    with patch("nexus.vision_provider.OpenAI", return_value=fake_client):
        provider = QwenVisionProvider(
            api_key="test",
            api_base="https://qwen.example/v1",
            primary_model="qwen-vl",
            attempts_per_model=3,
            retry_base_seconds=0,
        )
        observation = provider.analyze(b"jpeg", width=800, height=600)

    assert observation.visible_state == "Desktop"
    assert observation.model == "qwen-vl"
    assert fake_client.chat.completions.create.call_count == 2


def test_google_stream_removed_is_a_remote_deadline() -> None:
    assert is_remote_deadline_error("504 Stream removed (Deadline Exceeded)")
    assert is_remote_deadline_error(RuntimeError("Deadline Exceeded"))
    assert not is_remote_deadline_error("HTTP 403 Forbidden")
