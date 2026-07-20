# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Typed action ledger and deterministic completion verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping


SUCCESS_STATUSES = frozenset({"success", "completed", "ok", "verified"})
FAILURE_STATUSES = frozenset(
    {"error", "failed", "cancelled", "denied", "blocked", "approval_required"}
)
BLOCKED_ERROR_CODES = frozenset(
    {"APPROVAL_REQUIRED", "AUTH_REQUIRED", "APPROVAL_DENIED"}
)

GUI_MUTATIONS = frozenset(
    {
        "open_browser",
        "left_click",
        "right_click",
        "double_click",
        "triple_click",
        "type_text",
        "press_key",
        "scroll_screen",
        "drag",
        "playwright_navigate",
        "playwright_click",
        "playwright_type",
    }
)
VISUAL_VERIFIERS = frozenset(
    {
        "take_screenshot",
        "playwright_get_text",
        "playwright_wait_for",
        "playwright_snapshot",
        "playwright_verify",
    }
)
ARTIFACT_TOOLS = frozenset(
    {
        "publish_html_artifact",
        "generate_pdf_report",
        "generate_excel_report",
        "generate_docx_report",
        "save_as_artifact",
    }
)
SOURCE_TOOLS = frozenset(
    {
        "web_search",
        "tavily_search",
        "scrape_web_page",
        "search_sources",
    }
)

# Tools that are interchangeable for satisfying the same goal. A failure by one
# member is considered recovered when a later action by any member (or the same
# tool) succeeds — not just the identical tool name. This lets the agent work
# around a failed tool (e.g. web_search -> tavily_search) without the completion
# verifier vetoing an otherwise-correct turn.
_CAPABILITY_GROUPS = (SOURCE_TOOLS, ARTIFACT_TOOLS)


def _same_capability_group(candidate: str, failed: str) -> bool:
    if candidate == failed:
        return True
    return any(
        candidate in group and failed in group for group in _CAPABILITY_GROUPS
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _artifact_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    artifacts: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, Mapping):
            artifacts.append(dict(item))
        elif str(item).strip():
            artifacts.append({"path": str(item)})
    return artifacts


def _verification_method(tool_name: str) -> str:
    if tool_name in GUI_MUTATIONS:
        return "dom_or_screen_state"
    if tool_name in ARTIFACT_TOOLS:
        return "artifact_exists"
    if tool_name in SOURCE_TOOLS:
        return "source_result"
    if tool_name in {"terminal_worker", "desktop_worker"}:
        return "worker_evidence"
    if tool_name.startswith(("gmail_", "calendar_", "tasks_", "github_")):
        return "connector_result"
    return "tool_result"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    backoff_seconds: float = 1.0
    switch_strategy_on_repeat: bool = True


@dataclass(frozen=True)
class ActionDecision:
    action_id: str
    action: str
    expected_outcome: str
    verification_method: str
    retry_policy: RetryPolicy
    completion_condition: str
    safe_arguments: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def from_tool_call(
        cls,
        *,
        action_id: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
    ) -> "ActionDecision":
        args = dict(arguments or {})
        request = str(args.pop("request", "") or "").strip()
        expected = str(args.pop("expected_outcome", "") or "").strip()
        completion = str(args.pop("completion_condition", "") or "").strip()
        verification = str(args.pop("verification_method", "") or "").strip()
        return cls(
            action_id=action_id,
            action=tool_name,
            expected_outcome=expected
            or (request[:300] if request else f"{tool_name} returns successful evidence"),
            verification_method=verification or _verification_method(tool_name),
            retry_policy=RetryPolicy(),
            completion_condition=completion
            or f"Typed {tool_name} result confirms the expected state",
            safe_arguments={
                str(key): (
                    value
                    if isinstance(value, (bool, int, float)) or value is None
                    else str(value)[:500]
                )
                for key, value in args.items()
            },
        )


@dataclass(frozen=True)
class ActionObservation:
    action_id: str
    tool: str
    status: str
    evidence: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    retryable: bool = False
    error_code: str = ""
    verified: bool = False
    task_state: dict[str, str] = field(default_factory=dict)
    observed_at: str = field(default_factory=_utcnow)

    @classmethod
    def from_tool_result(
        cls,
        *,
        action_id: str,
        tool_name: str,
        result: Mapping[str, Any] | None,
        fallback_summary: str = "",
    ) -> "ActionObservation":
        payload = dict(result or {})
        detail = payload.get("detail")
        detail_map = dict(detail) if isinstance(detail, Mapping) else {}
        metadata = payload.get("metadata")
        metadata_map = dict(metadata) if isinstance(metadata, Mapping) else {}
        nested_task_state = metadata_map.get("state")
        if isinstance(nested_task_state, Mapping):
            metadata_map = {**metadata_map, **dict(nested_task_state)}
        task_state = {
            key: str(metadata_map[key])
            for key in _TASK_STATE_METADATA_KEYS
            if metadata_map.get(key) is not None
        }
        status = str(payload.get("status") or "success").strip().lower()
        summary = str(
            payload.get("summary")
            or payload.get("description")
            or fallback_summary
            or ""
        ).strip()
        evidence = _text_list(payload.get("evidence") or detail_map.get("evidence"))
        if summary and summary not in evidence:
            evidence.insert(0, summary)
        artifacts = _artifact_list(
            payload.get("artifacts")
            or detail_map.get("artifacts")
            or metadata_map.get("artifacts")
        )
        if tool_name in ARTIFACT_TOOLS and status in SUCCESS_STATUSES and not artifacts:
            candidate = (
                payload.get("output_path")
                or detail_map.get("output_path")
                or metadata_map.get("output_path")
                or payload.get("url")
                or detail_map.get("url")
            )
            artifacts = _artifact_list(candidate or {"tool": tool_name})
        remaining = _text_list(
            payload.get("remaining_work") or detail_map.get("remaining_work")
        )
        error_code = str(payload.get("error_code") or "").strip()
        verified_value = (
            payload.get("verified")
            if "verified" in payload
            else detail_map.get("verified", metadata_map.get("verified"))
        )
        verified = bool(
            verified_value
            if verified_value is not None
            else tool_name in VISUAL_VERIFIERS and status in SUCCESS_STATUSES
        )
        return cls(
            action_id=action_id,
            tool=tool_name,
            status=status,
            evidence=[item[:1000] for item in evidence[:12]],
            artifacts=artifacts[:20],
            remaining_work=[item[:500] for item in remaining[:20]],
            retryable=bool(
                payload.get("retryable")
                or detail_map.get("retryable")
                or metadata_map.get("retryable")
            ),
            error_code=error_code,
            verified=verified,
            task_state=task_state,
        )


@dataclass
class ActionRecord:
    decision: ActionDecision
    observation: ActionObservation | None = None


@dataclass
class ActionLedger:
    records: list[ActionRecord] = field(default_factory=list)

    def start(self, decision: ActionDecision) -> None:
        self.records.append(ActionRecord(decision=decision))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ActionLedger":
        ledger = cls()
        for raw in (value or {}).get("records", []):
            if not isinstance(raw, Mapping):
                continue
            decision_data = raw.get("decision")
            if not isinstance(decision_data, Mapping):
                continue
            retry_data = decision_data.get("retry_policy")
            retry = (
                RetryPolicy(**dict(retry_data))
                if isinstance(retry_data, Mapping)
                else RetryPolicy()
            )
            try:
                decision = ActionDecision(
                    action_id=str(decision_data.get("action_id") or ""),
                    action=str(decision_data.get("action") or "unknown"),
                    expected_outcome=str(
                        decision_data.get("expected_outcome") or ""
                    ),
                    verification_method=str(
                        decision_data.get("verification_method") or "tool_result"
                    ),
                    retry_policy=retry,
                    completion_condition=str(
                        decision_data.get("completion_condition") or ""
                    ),
                    safe_arguments=(
                        dict(decision_data.get("safe_arguments") or {})
                        if isinstance(
                            decision_data.get("safe_arguments"), Mapping
                        )
                        else {}
                    ),
                    created_at=str(decision_data.get("created_at") or _utcnow()),
                )
            except (TypeError, ValueError):
                continue
            observation = None
            observation_data = raw.get("observation")
            if isinstance(observation_data, Mapping):
                try:
                    observation = ActionObservation(
                        action_id=str(observation_data.get("action_id") or ""),
                        tool=str(observation_data.get("tool") or decision.action),
                        status=str(observation_data.get("status") or "error"),
                        evidence=_text_list(observation_data.get("evidence")),
                        artifacts=_artifact_list(observation_data.get("artifacts")),
                        remaining_work=_text_list(
                            observation_data.get("remaining_work")
                        ),
                        retryable=bool(observation_data.get("retryable")),
                        error_code=str(observation_data.get("error_code") or ""),
                        verified=bool(observation_data.get("verified")),
                        task_state=(
                            {
                                key: str(item)
                                for key, item in dict(
                                    observation_data.get("task_state") or {}
                                ).items()
                                if key in _TASK_STATE_METADATA_KEYS and item is not None
                            }
                            if isinstance(observation_data.get("task_state"), Mapping)
                            else {}
                        ),
                        observed_at=str(
                            observation_data.get("observed_at") or _utcnow()
                        ),
                    )
                except (TypeError, ValueError):
                    observation = None
            ledger.records.append(
                ActionRecord(decision=decision, observation=observation)
            )
        return ledger

    def finish(self, observation: ActionObservation) -> None:
        for record in reversed(self.records):
            if (
                record.decision.action_id == observation.action_id
                and record.observation is None
            ):
                record.observation = observation
                return
        self.records.append(
            ActionRecord(
                decision=ActionDecision.from_tool_call(
                    action_id=observation.action_id,
                    tool_name=observation.tool,
                    arguments={},
                ),
                observation=observation,
            )
        )

    def latest_unresolved_failures(self) -> list[ActionObservation]:
        unresolved: list[ActionObservation] = []
        for index, record in enumerate(self.records):
            observation = record.observation
            if observation is None:
                continue
            if observation.status not in FAILURE_STATUSES:
                continue
            recovered = any(
                later.observation is not None
                and later.observation.status in SUCCESS_STATUSES
                and (
                    _same_capability_group(
                        later.decision.action, record.decision.action
                    )
                    or (
                        observation.error_code == "SCREEN_VERIFICATION_REQUIRED"
                        and later.decision.action in VISUAL_VERIFIERS
                    )
                )
                for later in self.records[index + 1 :]
            )
            if not recovered:
                unresolved.append(observation)
        return unresolved

    def has_fresh_gui_verification(self) -> bool:
        last_mutation = -1
        last_verification = -1
        for index, record in enumerate(self.records):
            if record.decision.action in GUI_MUTATIONS:
                last_mutation = index
            if (
                record.decision.action in VISUAL_VERIFIERS
                and record.observation is not None
                and record.observation.status in SUCCESS_STATUSES
                and record.observation.verified
            ):
                last_verification = index
        return last_mutation < 0 or last_verification > last_mutation

    def artifacts(self) -> list[dict[str, Any]]:
        return [
            artifact
            for record in self.records
            if record.observation is not None
            for artifact in record.observation.artifacts
        ]

    def remaining_work(self) -> list[str]:
        values: list[str] = []
        for record in self.records:
            if record.observation:
                values.extend(record.observation.remaining_work)
        return list(dict.fromkeys(item for item in values if item.strip()))

    def successful_tools(self) -> set[str]:
        return {
            record.decision.action
            for record in self.records
            if record.observation is not None
            and record.observation.status in SUCCESS_STATUSES
        }

    def requires_source_evidence(self) -> bool:
        """Derive source requirements from durable task metadata, never prompt text."""
        return any(
            record.observation is not None
            and record.observation.status in SUCCESS_STATUSES
            and record.observation.task_state.get("task_type") == "deep_research"
            for record in self.records
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [
                {
                    "decision": asdict(record.decision),
                    "observation": (
                        asdict(record.observation) if record.observation else None
                    ),
                }
                for record in self.records
            ]
        }


@dataclass(frozen=True)
class CompletionVerification:
    verified: bool
    status: str
    method: str
    summary: str
    error_code: str = ""
    evidence: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ARTIFACT_REQUEST = re.compile(
    r"(?:\b(?:create|generate|build|make|export|produce)\b.{0,40}"
    r"\b(?:pdf|xlsx|spreadsheet|docx|document|html|report|artifact|file)\b"
    r"|\.pdf\b|\.xlsx\b|\.docx\b|\.html?\b)",
    re.IGNORECASE,
)
_TASK_STATE_METADATA_KEYS = frozenset({"task_type", "stage", "review_status"})


def verify_completion(
    *,
    request: str,
    final_response: str | None,
    ledger: ActionLedger,
) -> CompletionVerification:
    """Verify task completion from observable runtime evidence."""
    response = str(final_response or "").strip()
    if not response:
        return CompletionVerification(
            verified=False,
            status="failed",
            method="final_response",
            summary="The model ended without a final response.",
            error_code="MISSING_FINAL_RESPONSE",
            remaining_work=["Produce a final response grounded in tool evidence."],
            retryable=True,
        )

    failures = ledger.latest_unresolved_failures()
    if failures:
        blocked = next(
            (
                failure
                for failure in failures
                if failure.error_code in BLOCKED_ERROR_CODES
            ),
            None,
        )
        failure = blocked or failures[-1]
        return CompletionVerification(
            verified=False,
            status="blocked" if blocked else "failed",
            method="tool_result",
            summary=(
                f"Completion rejected because {failure.tool} has an unresolved "
                f"{failure.status} result."
            ),
            error_code=failure.error_code or "UNRESOLVED_TOOL_ERROR",
            evidence=failure.evidence[:4],
            remaining_work=failure.remaining_work
            or [f"Resolve or safely recover from {failure.tool}."],
            retryable=failure.retryable or blocked is None,
        )

    remaining = ledger.remaining_work()
    if remaining:
        return CompletionVerification(
            verified=False,
            status="partial",
            method="worker_evidence",
            summary="A worker reported unfinished work.",
            error_code="REMAINING_WORK",
            remaining_work=remaining,
            retryable=True,
        )

    if not ledger.has_fresh_gui_verification():
        return CompletionVerification(
            verified=False,
            status="failed",
            method="dom_or_screen_state",
            summary="The final browser or desktop mutation was not verified.",
            error_code="STALE_SCREEN_STATE",
            remaining_work=[
                "Verify the current state with Playwright DOM evidence or a fresh screenshot."
            ],
            retryable=True,
        )

    if _ARTIFACT_REQUEST.search(request) and not ledger.artifacts():
        return CompletionVerification(
            verified=False,
            status="failed",
            method="artifact_exists",
            summary="The request requires a deliverable, but no artifact was recorded.",
            error_code="MISSING_ARTIFACT",
            remaining_work=["Create and publish the requested artifact."],
            retryable=True,
        )

    if ledger.requires_source_evidence():
        successful = ledger.successful_tools()
        if not (successful & SOURCE_TOOLS) or not re.search(r"https?://", response):
            return CompletionVerification(
                verified=False,
                status="failed",
                method="source_result",
                summary="Research completion requires source-tool evidence and cited URLs.",
                error_code="MISSING_SOURCE_EVIDENCE",
                remaining_work=["Gather source evidence and cite the URLs in the final response."],
                retryable=True,
            )

    return CompletionVerification(
        verified=True,
        status="completed",
        method="evidence_ledger",
        summary="Requested state is supported by the action ledger.",
        evidence=[
            f"{record.decision.action}: {record.observation.status}"
            for record in ledger.records
            if record.observation is not None
        ][-8:],
    )


__all__ = [
    "ActionDecision",
    "ActionLedger",
    "ActionObservation",
    "CompletionVerification",
    "RetryPolicy",
    "verify_completion",
]
