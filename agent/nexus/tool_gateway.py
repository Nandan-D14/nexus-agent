# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tool gateway — centralized policy enforcement for agent tools.

The agent currently calls ``evaluate_tool_policy`` from a few places, but
that helper is just a function: nothing forces every tool call to go
through it. The gateway in this module turns policy enforcement into a
*decorator* that wraps a tool function. Once a tool is wrapped, every
invocation — by ADK, by tests, by future code paths — is checked against
:func:`nexus.policy.evaluate_tool_policy` before the underlying function
runs.

Decisions:

  * ``allow``           → the tool runs normally.
  * ``deny``            → the tool returns a structured "blocked" result
                          and the underlying function never executes.
  * ``require_approval`` → in *manual* mode the call is also blocked with
                          a clear message asking the user to switch to
                          Auto Mode or approve via the UI; this keeps the
                          gateway safe by default. The full
                          background-task approval flow lives in the
                          orchestrator and can supersede this when wired.

Why a decorator?
  - It makes the security boundary obvious: every wrapped tool is
    enforced.
  - It keeps tool authors from having to remember to call the policy
    helper.
  - It composes with :func:`nexus.tools.base.normalized_tool` so the
    blocked output still matches the normalized schema ADK expects.

Auditability:
  Every non-allow decision is logged at WARNING with a structured payload
  (tool, action, risk, reason). Downstream we can connect this to an
  audit Firestore collection without changing call sites.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable

from nexus.policy import ToolPolicyDecision, evaluate_tool_policy

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 120.0
APPROVAL_POLL_SECONDS = 2.0


def _denied_result(tool_name: str, decision: ToolPolicyDecision) -> dict[str, Any]:
    """Standard structured response for blocked tool calls."""
    return {
        "status": "blocked",
        "summary": f"{tool_name} blocked by policy: {decision.reason}",
        "detail": {
            "tool": tool_name,
            "policy_action": decision.action,
            "risk": decision.risk,
            "reason": decision.reason,
        },
        "metadata": {"policy_action": decision.action, "risk": decision.risk},
    }


def _budget_result(tool_name: str, guard: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "summary": guard.exhausted_reason or "Durable run budget exhausted.",
        "detail": {
            "tool": tool_name,
            "retryable": False,
            "remaining_work": "Resume from the saved durable checkpoint with a new budget.",
            "budget": guard.checkpoint(),
        },
        "metadata": {"tool": tool_name, "budget": guard.checkpoint()},
        "error_code": guard.exhausted_code or "BUDGET_EXHAUSTED",
        "suggested_alternatives": [],
    }


def _consume_tool_budget(tool_name: str) -> dict[str, Any] | None:
    try:
        from nexus.tools._context import get_task_budget_guard

        guard = get_task_budget_guard()
    except Exception:
        guard = None
    if guard is None or guard.before_tool_call(tool_name):
        return None
    return _budget_result(tool_name, guard)


def _approval_required_result(tool_name: str, decision: ToolPolicyDecision) -> dict[str, Any]:
    """Standard response when the tool needs human approval but isn't auto."""
    return {
        "status": "approval_required",
        "summary": (
            f"{tool_name} requires approval: {decision.reason}. "
            "Approve via the UI or switch this task to Auto Mode."
        ),
        "detail": {
            "tool": tool_name,
            "policy_action": decision.action,
            "risk": decision.risk,
            "reason": decision.reason,
            "retryable": True,
            "remaining_work": f"Approve the exact blocked {tool_name} action.",
        },
        "metadata": {"policy_action": decision.action, "risk": decision.risk},
        "error_code": "APPROVAL_REQUIRED",
        "suggested_alternatives": [],
    }


def _approval_denied_result(tool_name: str, decision: ToolPolicyDecision) -> dict[str, Any]:
    return {
        "status": "blocked",
        "summary": f"{tool_name} was not approved: {decision.reason}",
        "detail": {
            "tool": tool_name,
            "policy_action": decision.action,
            "risk": decision.risk,
            "reason": decision.reason,
        },
        "metadata": {"policy_action": decision.action, "risk": decision.risk},
        "error_code": "APPROVAL_DENIED",
        "suggested_alternatives": [],
    }


def _resolve_autonomy_mode() -> str | None:
    """Pull autonomy mode from the active runtime context, if any."""
    try:
        from nexus.tools._context import get_runtime_config

        runtime_config = get_runtime_config()
        return getattr(runtime_config, "autonomy_mode", None)
    except Exception:
        return None


def _tool_not_selected_result(tool_name: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "summary": (
            f"{tool_name} is not in the user-selected tool set for this turn. "
            "Use only the tools the user enabled, or ask them to enable it."
        ),
        "detail": {
            "tool": tool_name,
            "reason": "Tool was not selected in the composer tool picker.",
            "retryable": False,
        },
        "metadata": {"policy_action": "deny", "reason": "tool_not_selected"},
        "error_code": "TOOL_NOT_SELECTED",
        "suggested_alternatives": [
            "Continue with an allowed tool from the user-selected set.",
            "Ask the user to enable this tool in the composer + menu.",
        ],
    }


def _check_tool_allowlist(tool_name: str, func: Callable | None = None) -> dict[str, Any] | None:
    """Return a blocked result when the tool is outside the per-turn allowlist."""
    try:
        from nexus.tool_catalog import is_tool_allowed
        from nexus.tools._context import get_tool_allowlist

        allowlist = get_tool_allowlist()
        connection_id = getattr(func, "_connection_id", None) if func is not None else None
        if is_tool_allowed(tool_name, allowlist, connection_id=connection_id):
            return None
        return _tool_not_selected_result(tool_name)
    except Exception:
        # Fail open if context/catalog is unavailable — never brick a turn.
        return None


def _bind_args(func: Callable, args: tuple, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Best-effort: turn (*args, **kwargs) into a name -> value mapping
    so the policy can inspect them by name (e.g. ``command``)."""
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return {
            key: value
            for key, value in bound.arguments.items()
            if not str(key).startswith("_")
        }
    except (TypeError, ValueError):
        # Fall back to kwargs only — better than nothing.
        return dict(kwargs)


def _log_decision(tool_name: str, decision: ToolPolicyDecision, args_view: dict[str, Any]) -> None:
    if decision.action == "allow":
        return
    logger.warning(
        "tool_policy_decision",
        extra={
            "tool": tool_name,
            "policy_action": decision.action,
            "risk": decision.risk,
            "reason": decision.reason,
            # Keep the audit log small; only include a tiny preview of the
            # arguments. ``run_command`` is the only one with a long string
            # field today.
            "args_preview": _preview_args(args_view),
        },
    )


def _is_secret_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(
        marker in lowered
        for marker in ("token", "secret", "password", "api_key", "apikey", "authorization")
    )


def _preview_args(args_view: dict[str, Any], *, limit: int = 240) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key, value in args_view.items():
        if _is_secret_key(str(key)):
            preview[key] = "***"
            continue
        if isinstance(value, str):
            preview[key] = value if len(value) <= limit else value[: limit - 1] + "…"
        elif isinstance(value, (int, float, bool)) or value is None:
            preview[key] = value
        else:
            preview[key] = type(value).__name__
    return preview


def _canonical_approval_args(args_view: dict[str, Any]) -> dict[str, Any]:
    """Secret-safe args retained for exact approved-action resume matching."""
    canonical: dict[str, Any] = {}
    for key, value in args_view.items():
        if _is_secret_key(str(key)):
            canonical[key] = "***"
            continue
        if isinstance(value, str):
            # Keep full command/path strings for hash-stable resume; truncate only
            # extremely large payloads so Firestore docs stay bounded.
            canonical[key] = value if len(value) <= 8000 else value[:7999] + "…"
        elif isinstance(value, (int, float, bool)) or value is None:
            canonical[key] = value
        elif isinstance(value, (list, tuple)):
            canonical[key] = [
                item if isinstance(item, (str, int, float, bool)) or item is None else type(item).__name__
                for item in list(value)[:40]
            ]
        elif isinstance(value, dict):
            canonical[key] = _preview_args(value, limit=500)
        else:
            canonical[key] = type(value).__name__
    return canonical


def _approval_description(tool_name: str, decision: ToolPolicyDecision) -> str:
    return f"{tool_name} requires approval: {decision.reason}"


async def _await_background_task_approval(tool_name: str, decision: ToolPolicyDecision) -> bool | None:
    try:
        from nexus.tools._context import get_bg_task_manager

        manager = get_bg_task_manager()
    except Exception:
        manager = None
    if manager is None:
        return None
    _, approved = await manager.request_permission(
        _approval_description(tool_name, decision),
        estimated_seconds=int(APPROVAL_TIMEOUT_SECONDS),
        agent="policy",
    )
    return approved


async def _await_durable_approval(
    tool_name: str,
    decision: ToolPolicyDecision,
    args_view: dict[str, Any],
) -> bool | str | None:
    try:
        from nexus.tools._context import (
            get_owner_id,
            get_production_task_repository,
            get_run_id,
            get_send_json,
            get_task_id,
        )

        repository = get_production_task_repository()
        task_id = get_task_id()
        owner_id = get_owner_id()
        try:
            run_id = get_run_id()
        except Exception:
            run_id = None
        send_json = get_send_json()
    except Exception:
        return None

    if repository is None or not task_id.startswith("task_") or not owner_id:
        return None

    from nexus.production_tasks import approval_action_hash

    action_hash = approval_action_hash(tool_name, args_view)
    try:
        consume_action = getattr(repository, "consume_approved_action", None)
        existing = (
            await consume_action(
                task_id=task_id,
                owner_id=owner_id,
                action_hash=action_hash,
            )
            if callable(consume_action)
            else None
        )
        if existing is not None:
            logger.info(
                "Consumed exact approval decision for %s on task %s",
                tool_name,
                task_id,
            )
            return bool(existing.approved)
    except Exception:
        logger.warning(
            "Failed to consume existing approval for %s",
            tool_name,
            exc_info=True,
        )

    approval = await repository.create_approval(
        task_id=task_id,
        owner_id=owner_id,
        description=_approval_description(tool_name, decision),
        risk=decision.risk,
        metadata={
            "tool": tool_name,
            "args_preview": _preview_args(args_view),
            "canonical_args": _canonical_approval_args(args_view),
            "run_id": run_id,
            "action_hash": action_hash,
        },
    )
    if send_json is not None:
        await send_json(
            {
                "type": "permission_request",
                "task_id": approval.approval_id,
                "approval_id": approval.approval_id,
                "durable_task_id": task_id,
                "description": approval.description,
                "estimated_seconds": int(APPROVAL_TIMEOUT_SECONDS),
                "agent": "policy",
                "risk": approval.risk,
            }
        )

    deadline = time.monotonic() + APPROVAL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        current = await repository.get_approval(
            task_id=task_id,
            approval_id=approval.approval_id,
            owner_id=owner_id,
        )
        if current and current.status in {"approved", "denied"}:
            if not current.approved:
                return False
            consume_action = getattr(
                repository,
                "consume_approved_action",
                None,
            )
            if not callable(consume_action):
                return True
            consumed = await consume_action(
                task_id=task_id,
                owner_id=owner_id,
                action_hash=action_hash,
                approval_id=approval.approval_id,
            )
            return consumed is not None
        await asyncio.sleep(APPROVAL_POLL_SECONDS)
    return "pending"


async def _await_approval(
    tool_name: str,
    decision: ToolPolicyDecision,
    args_view: dict[str, Any],
) -> bool | str | None:
    durable = await _await_durable_approval(tool_name, decision, args_view)
    if durable is not None:
        return durable

    return await _await_background_task_approval(tool_name, decision)


def _check_verification_warning(tool_name: str) -> str | None:
    """Check if the perception-action loop should warn before this tool runs."""
    try:
        from nexus.tools.verification import should_verify_before_action
        return should_verify_before_action(tool_name)
    except Exception:
        return None


def _inject_warning(result: Any, warning: str) -> Any:
    """Prepend a verification warning to a tool's result summary."""
    if isinstance(result, dict):
        existing_summary = result.get("summary", "")
        result["summary"] = f"{warning}\n\n{existing_summary}" if existing_summary else warning
        if "verification_warning" not in result:
            result["verification_warning"] = warning
    return result


def _verification_required_result(tool_name: str, reason: str) -> dict[str, Any]:
    """Block a blind mutation and return a typed recovery instruction."""
    return {
        "status": "error",
        "summary": reason,
        "detail": {
            "tool": tool_name,
            "verified": False,
            "retryable": True,
            "remaining_work": f"Observe current state, then retry {tool_name}.",
        },
        "metadata": {
            "tool": tool_name,
            "verification_required": True,
        },
        "error_code": "SCREEN_VERIFICATION_REQUIRED",
        "suggested_alternatives": [
            "playwright_snapshot",
            "playwright_verify",
            "take_screenshot",
        ],
    }


def _resolve_resource_locks():
    try:
        from nexus.tools._context import get_subagent_resource_locks

        return get_subagent_resource_locks()
    except Exception:
        return None


def gated_tool(func: Callable) -> Callable:
    """Wrap a tool callable so every invocation passes policy enforcement.

    The wrapper preserves the original function's name and signature (via
    :func:`functools.wraps`), which is important because Google ADK
    derives tool schemas from the function signature/docstring.
    """
    tool_name = getattr(func, "__name__", "tool")

    is_async = asyncio.iscoroutinefunction(func)

    async def _invoke_underlying(*args: Any, **kwargs: Any) -> Any:
        if is_async:
            return await func(*args, **kwargs)
        # Keep sync tools off the event-loop thread when they may block on I/O.
        return await asyncio.to_thread(func, *args, **kwargs)

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        blocked = _check_tool_allowlist(tool_name, func)
        if blocked is not None:
            return blocked
        budget_block = _consume_tool_budget(tool_name)
        if budget_block is not None:
            return budget_block
        args_view = _bind_args(func, args, kwargs)
        decision = evaluate_tool_policy(
            tool_name,
            args_view,
            autonomy_mode=_resolve_autonomy_mode(),
        )
        _log_decision(tool_name, decision, args_view)
        if decision.action == "deny":
            return _denied_result(tool_name, decision)
        if decision.action == "require_approval":
            approved = await _await_approval(tool_name, decision, args_view)
            if approved is True:
                warning = _check_verification_warning(tool_name)
                if warning:
                    return _verification_required_result(tool_name, warning)
                locks = _resolve_resource_locks()
                if locks is None:
                    return await _invoke_underlying(*args, **kwargs)
                async with locks.async_lock(tool_name):
                    return await _invoke_underlying(*args, **kwargs)
            if approved is False:
                return _approval_denied_result(tool_name, decision)
            return _approval_required_result(tool_name, decision)

        # Perception-action loop: never execute a blind shared-state mutation.
        warning = _check_verification_warning(tool_name)
        if warning:
            return _verification_required_result(tool_name, warning)
        locks = _resolve_resource_locks()
        if locks is None:
            return await _invoke_underlying(*args, **kwargs)
        async with locks.async_lock(tool_name):
            return await _invoke_underlying(*args, **kwargs)

    return async_wrapper


def gate_tools(tools: list[Callable]) -> list[Callable]:
    """Apply :func:`gated_tool` to every callable in ``tools``.

    Non-callable entries (e.g. ADK ``google_search`` builtin objects)
    are returned untouched so we don't accidentally break ADK's
    introspection on them.
    """
    wrapped: list[Callable] = []
    for tool in tools:
        if callable(tool):
            try:
                wrapped.append(gated_tool(tool))
                continue
            except Exception:
                logger.warning(
                    "Failed to wrap tool %s with gated_tool; passing through.",
                    getattr(tool, "__name__", repr(tool)),
                    exc_info=True,
                )
        wrapped.append(tool)
    return wrapped


__all__ = ["gated_tool", "gate_tools"]
