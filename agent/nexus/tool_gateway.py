# Copyright (c) 2026 nandan-d14. All rights reserved.
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

from nexus import run_progress
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


def _approval_expired_result(tool_name: str, decision: ToolPolicyDecision) -> dict[str, Any]:
    """Approval wait ended with no decision. Do not leave the run waiting."""
    return {
        "status": "error",
        "summary": (
            f"{tool_name} approval timed out, so the action was not run. "
            "The rest of this turn can finish without it."
        ),
        "detail": {
            "tool": tool_name,
            "policy_action": decision.action,
            "risk": decision.risk,
            "reason": decision.reason,
            "retryable": False,
            "remaining_work": [],
        },
        "metadata": {"policy_action": decision.action, "risk": decision.risk},
        "error_code": "APPROVAL_EXPIRED",
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
    from nexus.tool_catalog import is_tool_allowed
    from nexus.tools._context import get_tool_allowlist

    try:
        allowlist = get_tool_allowlist()
    except Exception:
        logger.warning(
            "tool_allowlist_unavailable tool=%s — failing closed",
            tool_name,
            exc_info=True,
        )
        return _tool_not_selected_result(tool_name)
    try:
        connection_id = getattr(func, "_connection_id", None) if func is not None else None
        if is_tool_allowed(tool_name, allowlist, connection_id=connection_id):
            return None
        return _tool_not_selected_result(tool_name)
    except Exception:
        logger.warning(
            "tool_allowlist_check_failed tool=%s — failing closed",
            tool_name,
            exc_info=True,
        )
        return _tool_not_selected_result(tool_name)


def _bind_args(func: Callable, args: tuple, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Best-effort: turn (*args, **kwargs) into a name -> value mapping
    so the policy can inspect them by name (e.g. ``command``)."""
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        view = {
            key: value
            for key, value in bound.arguments.items()
            if not str(key).startswith("_")
        }
        # Recover positional command when signature binding drops it: policy
        # must never see an empty command for run_command.
        if not str(view.get("command") or "").strip() and args:
            for item in list(args) + list(kwargs.values()):
                if isinstance(item, str) and item.strip():
                    view.setdefault("command", item)
                    break
        return view
    except (TypeError, ValueError):
        # Fail closed for run_command: missing command view must not become
        # "Low-risk shell command". Record raw text when available.
        fallback = dict(kwargs)
        if args:
            for item in args:
                if isinstance(item, str) and item.strip():
                    fallback.setdefault("command", item)
                    break
            else:
                fallback.setdefault("_unbound_positional", True)
        return fallback


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
    from nexus.redact import is_secret_key

    return is_secret_key(key)


def _preview_args(args_view: dict[str, Any], *, limit: int = 240) -> dict[str, Any]:
    from nexus.redact import redact_inline_values

    preview: dict[str, Any] = {}
    for key, value in args_view.items():
        if _is_secret_key(str(key)):
            preview[key] = "***"
            continue
        if isinstance(value, str):
            cleaned = redact_inline_values(value)
            preview[key] = cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"
        elif isinstance(value, (int, float, bool)) or value is None:
            preview[key] = value
        else:
            preview[key] = type(value).__name__
    return preview


def _canonical_approval_args(args_view: dict[str, Any]) -> dict[str, Any]:
    """Secret-safe args retained for exact approved-action resume matching."""
    from nexus.redact import redact_inline_values

    canonical: dict[str, Any] = {}
    for key, value in args_view.items():
        if _is_secret_key(str(key)):
            canonical[key] = "***"
            continue
        if isinstance(value, str):
            cleaned = redact_inline_values(value)
            # Keep full command/path strings for hash-stable resume; truncate only
            # extremely large payloads so Firestore docs stay bounded.
            canonical[key] = cleaned if len(cleaned) <= 8000 else cleaned[:7999] + "…"
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
        from nexus.tools._context import get_bg_task_manager, get_skip_confirmations

        if get_skip_confirmations():
            return True
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
            get_skip_confirmations,
            get_task_id,
        )

        if get_skip_confirmations():
            return True

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
        logger.info(
            "approval_requested tool=%s task=%s approval=%s risk=%s hash=%s",
            tool_name,
            task_id,
            approval.approval_id,
            approval.risk,
            action_hash,
        )
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
                "tool": tool_name,
                "action_hash": action_hash,
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
            logger.info(
                "approval_resolved tool=%s task=%s approval=%s approved=%s hash=%s",
                tool_name,
                task_id,
                approval.approval_id,
                bool(current.approved),
                action_hash,
            )
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

    try:
        from nexus.tools._context import mark_tool_approval_timed_out

        mark_tool_approval_timed_out(tool_name)
    except Exception:
        pass
    if send_json is not None:
        try:
            await send_json(
                {
                    "type": "approval_resolved",
                    "task_id": approval.approval_id,
                    "approval_id": approval.approval_id,
                    "approved": False,
                    "status": "timed_out",
                    "reason": "timeout",
                    "action_hash": action_hash,
                }
            )
        except Exception:
            logger.debug("Failed to emit approval timeout for %s", tool_name, exc_info=True)
    logger.warning(
        "approval_timed_out tool=%s task=%s approval=%s hash=%s",
        tool_name,
        task_id,
        approval.approval_id,
        action_hash,
    )
    try:
        await repository.resolve_approval(
            task_id=task_id,
            approval_id=approval.approval_id,
            owner_id=owner_id,
            approved=False,
        )
    except Exception:
        logger.debug("Failed to close timed-out approval %s", approval.approval_id, exc_info=True)
    return "expired"


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
    """Check if the agent must refresh its observation before this action."""
    try:
        from nexus.tools.verification import should_verify_before_action
        return should_verify_before_action(tool_name)
    except Exception:
        # Fail closed for GUI mutators: a broken verifier must not permit a
        # blind shared-state mutation.
        from nexus.tools.verification import _GUI_ACTIONS

        if tool_name in _GUI_ACTIONS:
            logger.warning(
                "verification_unavailable tool=%s — blocking blind mutation",
                tool_name,
                exc_info=True,
            )
            return (
                "Verification service unavailable. Observe with take_screenshot, "
                f"playwright_snapshot, or playwright_verify before '{tool_name}'."
            )
        return None


_UNTRUSTED_PRODUCER_TOOLS = frozenset(
    {
        "scrape_web_page",
        "web_search",
        "tavily_search",
        "search_sources",
        "desktop_worker",
        "take_screenshot",
        "playwright_get_text",
        "playwright_snapshot",
        "playwright_verify",
        "open_browser",
        "read_drive_file",
        "gmail_read",
        "github_read_file",
    }
)


def _is_untrusted_producer(tool_name: str) -> bool:
    if tool_name in _UNTRUSTED_PRODUCER_TOOLS:
        return True
    return str(tool_name).startswith("mcp__")


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


def _progress_run_id() -> str | None:
    """Run id for liveness tracking, or None outside a bound turn."""
    from nexus.tools._context import get_run_id

    try:
        return get_run_id() or None
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
        # The stall watchdogs read silence as a hang. A tool that legitimately
        # runs for minutes (sandbox provisioning, playwright install) must not
        # look identical to a wedged model stream, so bracket the call.
        run_id = _progress_run_id()
        run_progress.tool_started(run_id)
        try:
            if is_async:
                return await func(*args, **kwargs)
            # Keep sync tools off the event-loop thread when they may block on I/O.
            return await asyncio.to_thread(func, *args, **kwargs)
        finally:
            run_progress.tool_finished(run_id)

    async def _invoke_guarded(*args: Any, **kwargs: Any) -> Any:
        """Invoke the tool, converting an escaping raise into a tool error.

        Native tools are already protected by ``normalized_tool``'s catch-all,
        but approved MCP/ADK tools are not: any raise here used to propagate
        through the runner and kill the entire turn with a generic
        AGENT_ERROR. A failed tool call must be a ledger observation the
        planner can retry or route around — never a turn-ending exception.
        ``CancelledError`` still propagates so stall-watchdog cancellation
        keeps working.
        """
        try:
            return await _invoke_underlying(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from nexus.tools.base import (
                classify_exception_message,
                root_error_message,
            )

            message = root_error_message(exc)
            error_code, retryable = classify_exception_message(message)
            logger.exception(
                "Approved tool %s raised; converting to tool error", tool_name
            )
            return {
                "status": "error",
                "summary": f"{tool_name} failed during execution: {message}",
                "detail": {
                    "tool": tool_name,
                    "exception": type(exc).__name__,
                    "message": message,
                    "retryable": retryable,
                    "remaining_work": [
                        f"Retry {tool_name} with narrower inputs, "
                        "or use an alternative tool."
                    ],
                },
                "metadata": {"tool": tool_name},
                "error_code": error_code,
                "suggested_alternatives": [],
            }

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        blocked = _check_tool_allowlist(tool_name, func)
        if blocked is not None:
            return blocked
        budget_block = _consume_tool_budget(tool_name)
        if budget_block is not None:
            return budget_block
        args_view = _bind_args(func, args, kwargs)
        # Fail closed for run_command when the command text could not be
        # recovered: never treat it as low-risk.
        if tool_name == "run_command" and not str(args_view.get("command") or "").strip():
            if args_view.get("_unbound_positional"):
                return _denied_result(
                    tool_name,
                    ToolPolicyDecision(
                        "deny",
                        "Command text unavailable for policy inspection.",
                        "blocked",
                    ),
                )
        unattended: frozenset[str] = frozenset()
        try:
            from nexus.tools._context import get_unattended_tools

            unattended = get_unattended_tools()
        except Exception:
            unattended = frozenset()
        try:
            from nexus.tools._context import untrusted_content_in_scope

            untrusted_flag = untrusted_content_in_scope()
        except Exception:
            untrusted_flag = False
        decision = evaluate_tool_policy(
            tool_name,
            args_view,
            autonomy_mode=_resolve_autonomy_mode(),
            untrusted_input_in_scope=untrusted_flag,
            allowed_unattended_tools=unattended,
        )
        _log_decision(tool_name, decision, args_view)
        if decision.action == "deny":
            return _denied_result(tool_name, decision)
        if decision.action == "require_approval":
            from nexus.tools._context import tool_approval_timed_out

            if tool_approval_timed_out(tool_name):
                return _approval_expired_result(tool_name, decision)
            approved = await _await_approval(tool_name, decision, args_view)
            if approved is True:
                result = await _invoke_with_verification_and_locks(
                    tool_name, _invoke_underlying, args, kwargs
                )
                _mark_untrusted_producer(tool_name)
                return result
            if approved is False:
                return _approval_denied_result(tool_name, decision)
            if approved in {"pending", "expired"}:
                return _approval_expired_result(tool_name, decision)
            return _approval_required_result(tool_name, decision)

        # Perception-action loop: never execute a blind shared-state mutation.
        warning = _check_verification_warning(tool_name)
        if warning:
            return _verification_required_result(tool_name, warning)
        result = await _invoke_with_locks(tool_name, _invoke_underlying, args, kwargs)
        _mark_untrusted_producer(tool_name)
        return result

    return async_wrapper


def _tool_exception_result(tool_name: str, exc: BaseException) -> dict[str, Any]:
    """Convert an escaped tool raise into a ledger observation.

    Native tools are already protected by ``normalized_tool``'s catch-all,
    but approved MCP/ADK tools are not: any raise used to propagate through
    the runner and kill the entire turn with a generic AGENT_ERROR. A failed
    tool call must be an observation the planner can retry or route around --
    never a turn-ending exception. ``CancelledError`` is never converted so
    stall-watchdog cancellation keeps working.
    """
    from nexus.tools.base import (
        classify_exception_message,
        root_error_message,
    )

    message = root_error_message(exc)
    error_code, retryable = classify_exception_message(message)
    logger.exception("Tool %s raised; converting to tool error", tool_name)
    return {
        "status": "error",
        "summary": f"{tool_name} failed during execution: {message}",
        "detail": {
            "tool": tool_name,
            "exception": type(exc).__name__,
            "message": message,
            "retryable": retryable,
            "remaining_work": [
                f"Retry {tool_name} with narrower inputs, "
                "or use an alternative tool."
            ],
        },
        "metadata": {"tool": tool_name},
        "error_code": error_code,
        "suggested_alternatives": [],
    }


async def _invoke_with_locks(tool_name: str, invoke_fn, args, kwargs):
    try:
        locks = _resolve_resource_locks()
        if locks is None:
            return await invoke_fn(*args, **kwargs)
        async with locks.async_lock(tool_name):
            return await invoke_fn(*args, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _tool_exception_result(tool_name, exc)


async def _invoke_with_verification_and_locks(tool_name: str, invoke_fn, args, kwargs):
    warning = _check_verification_warning(tool_name)
    if warning:
        return _verification_required_result(tool_name, warning)
    return await _invoke_with_locks(tool_name, invoke_fn, args, kwargs)


def _mark_untrusted_producer(tool_name: str) -> None:
    if not _is_untrusted_producer(tool_name):
        return
    try:
        from nexus.tools._context import mark_untrusted_content_seen

        mark_untrusted_content_seen()
    except Exception:
        pass


def gate_tools(tools: list[Callable]) -> list[Callable]:
    """Apply :func:`gated_tool` to every callable in ``tools``.

    Non-callable entries (e.g. ADK ``google_search`` builtin objects)
    are returned untouched so we don't accidentally break ADK's
    introspection on them. Callable wrap failures fail closed with a
    blocked stub instead of an unwrapped passthrough.
    """
    wrapped: list[Callable] = []
    for tool in tools:
        if callable(tool):
            try:
                wrapped.append(gated_tool(tool))
                continue
            except Exception:
                tool_label = getattr(tool, "__name__", repr(tool))
                logger.warning(
                    "Failed to wrap tool %s with gated_tool; failing closed.",
                    tool_label,
                    exc_info=True,
                )

                @functools.wraps(tool)
                async def _blocked_stub(*args: Any, _tool_label: str = str(tool_label), **kwargs: Any) -> Any:
                    return {
                        "status": "blocked",
                        "summary": f"{_tool_label} blocked: policy wrapper unavailable.",
                        "detail": {"tool": _tool_label, "retryable": False},
                        "metadata": {"policy_action": "deny"},
                        "error_code": "POLICY_WRAP_FAILED",
                        "suggested_alternatives": [],
                    }

                wrapped.append(_blocked_stub)
                continue
        wrapped.append(tool)
    return wrapped


__all__ = ["gated_tool", "gate_tools"]
