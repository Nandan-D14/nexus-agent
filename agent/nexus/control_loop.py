# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Typed action ledger and deterministic completion verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping


SUCCESS_STATUSES = frozenset({"success", "completed", "ok", "verified"})
FAILURE_STATUSES = frozenset(
    {"error", "failed", "cancelled", "denied", "blocked", "approval_required"}
)
BLOCKED_ERROR_CODES = frozenset(
    {"APPROVAL_REQUIRED", "AUTH_REQUIRED", "APPROVAL_DENIED"}
)
# Timed-out optional side effects (e.g. github_push) must not wedge the turn.
SKIPPABLE_ERROR_CODES = frozenset({"APPROVAL_EXPIRED"})

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
        "publish_app_preview",
        "scaffold_web_project",
        "generate_pdf_report",
        "generate_excel_report",
        "generate_docx_report",
        "generate_pptx_report",
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
TERMINAL_TOOLS = frozenset(
    {
        "terminal_worker",
        "run_command",
        "bash",
    }
)
WORKSPACE_FILE_TOOLS = frozenset(
    {
        "write_workspace_file",
        "read_workspace_file",
        "list_workspace_files",
        "prepare_task_workspace",
    }
)

# Tools that are interchangeable for satisfying the same goal. A failure by one
# member is considered recovered when a later action by any member (or the same
# tool) succeeds — not just the identical tool name. This lets the agent work
# around a failed tool (e.g. web_search -> tavily_search) without the completion
# verifier vetoing an otherwise-correct turn.
_CAPABILITY_GROUPS = (SOURCE_TOOLS, ARTIFACT_TOOLS, TERMINAL_TOOLS, WORKSPACE_FILE_TOOLS)


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


def _citation_key(url: str | None, saved: str | None, idx: int) -> str:
    from urllib.parse import urlparse

    if url:
        try:
            host = urlparse(url).netloc.replace("www.", "")
            base = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
            if base:
                return f"{base}-{idx}"
        except Exception:
            pass
    if saved:
        base = re.sub(r"[^a-z0-9]+", "-", str(saved).lower().rsplit("/", 1)[-1]).strip("-")
        if base:
            return f"{base}-{idx}"
    return f"src-{idx}"


def _normalize_sources(
    *,
    explicit: Any,
    results: Any,
    tool_name: str,
    scrape_url: str | None,
    scrape_title: str | None,
    saved_path: str | None,
) -> list[dict[str, Any]]:
    """Build a structured source list {title,url,provider,verification,citation_key,saved_path?}.

    Accepts three shapes, provider-agnostic so any tool/worker/subagent/workflow
    that reports sources (explicit ``sources``), search results (``results``), or
    a captured page contributes uniformly.
    """
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(title, url, provider, verification, saved):
        url_s = str(url).strip() if url else ""
        saved_s = str(saved).strip() if saved else ""
        key = url_s.lower() or saved_s.lower()
        if not key or key in seen:
            return
        seen.add(key)
        idx = len(sources) + 1
        entry: dict[str, Any] = {
            "title": str(title or url_s or saved_s or f"source {idx}")[:300],
            "url": url_s or None,
            "provider": str(provider or tool_name or "")[:60],
            "verification": verification,
            "citation_key": _citation_key(url_s or None, saved_s or None, idx),
        }
        if saved_s:
            entry["saved_path"] = saved_s
        sources.append(entry)

    if isinstance(explicit, list):
        for item in explicit:
            if isinstance(item, Mapping):
                _add(
                    item.get("title"),
                    item.get("url"),
                    item.get("provider"),
                    str(item.get("verification") or "search_only"),
                    item.get("saved_path") or item.get("source"),
                )
    if isinstance(results, list):
        for item in results:
            if isinstance(item, Mapping):
                url = item.get("url")
                saved = item.get("saved_path") or item.get("source")
                verification = "captured" if saved and not url else "search_only"
                _add(item.get("title"), url, tool_name, verification, saved)
    if scrape_url or saved_path:
        _add(scrape_title, scrape_url, tool_name, "captured", saved_path)
    return sources[:30]


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
    sources: list[dict[str, Any]] = field(default_factory=list)
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
        # Scrape metadata only counts as a captured source for the scrape tool;
        # other tools (e.g. web_search) also carry a saved_path for their dump
        # which must not masquerade as an individually captured page.
        is_capture_tool = tool_name == "scrape_web_page"
        sources = _normalize_sources(
            explicit=(
                payload.get("sources")
                or detail_map.get("sources")
                or metadata_map.get("sources")
            ),
            results=(
                metadata_map.get("results")
                or detail_map.get("results")
                or payload.get("results")
            ),
            tool_name=tool_name,
            scrape_url=(
                (metadata_map.get("url") or detail_map.get("url") or payload.get("url"))
                if is_capture_tool
                else None
            ),
            scrape_title=(
                (metadata_map.get("title") or detail_map.get("title"))
                if is_capture_tool
                else None
            ),
            saved_path=(
                (metadata_map.get("saved_path") or detail_map.get("saved_path"))
                if is_capture_tool
                else None
            ),
        )
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
            sources=sources,
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
    turn_index: int = 0


@dataclass
class ActionLedger:
    records: list[ActionRecord] = field(default_factory=list)
    current_turn_index: int = 0

    def advance_turn(self) -> int:
        self.current_turn_index += 1
        return self.current_turn_index

    def start(self, decision: ActionDecision) -> None:
        self.records.append(ActionRecord(decision=decision, turn_index=self.current_turn_index))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ActionLedger":
        ledger = cls()
        data = value or {}
        ledger.current_turn_index = int(data.get("current_turn_index") or 0)
        for raw in data.get("records", []):
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
                        sources=[
                            dict(item)
                            for item in (observation_data.get("sources") or [])
                            if isinstance(item, Mapping)
                        ],
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
            turn_idx = int(raw.get("turn_index") or 0)
            ledger.records.append(
                ActionRecord(decision=decision, observation=observation, turn_index=turn_idx)
            )
        return ledger

    def finish(self, observation: ActionObservation) -> None:
        for record in reversed(self.records):
            if (
                record.decision.action_id == observation.action_id
                and record.observation is None
            ):
                record.observation = observation
                record.turn_index = self.current_turn_index
                return
        self.records.append(
            ActionRecord(
                decision=ActionDecision.from_tool_call(
                    action_id=observation.action_id,
                    tool_name=observation.tool,
                    arguments={},
                ),
                observation=observation,
                turn_index=self.current_turn_index,
            )
        )

    def latest_unresolved_failures(self, current_turn_only: bool = True) -> list[ActionObservation]:
        unresolved: list[ActionObservation] = []
        has_current_turn_records = any(
            getattr(r, "turn_index", 0) == self.current_turn_index for r in self.records
        )
        target_records = (
            [r for r in self.records if getattr(r, "turn_index", 0) == self.current_turn_index]
            if current_turn_only and has_current_turn_records
            else self.records
        )
        for index, record in enumerate(target_records):
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
                for later in target_records[index + 1 :]
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

    def all_sources(self) -> list[dict[str, Any]]:
        """Structured sources gathered by successful actions, deduped.

        Aggregates ``ActionObservation.sources`` across the ledger so that
        evidence gathered directly (web_search/scrape) or reported by a
        worker/subagent/workflow result all count uniformly.
        """
        seen: set[str] = set()
        collected: list[dict[str, Any]] = []
        for record in self.records:
            observation = record.observation
            if observation is None or observation.status not in SUCCESS_STATUSES:
                continue
            for source in observation.sources:
                key = str(
                    source.get("url")
                    or source.get("saved_path")
                    or source.get("citation_key")
                    or ""
                ).lower()
                if key and key not in seen:
                    seen.add(key)
                    collected.append(source)
        return collected

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
            "current_turn_index": self.current_turn_index,
            "records": [
                {
                    "turn_index": getattr(record, "turn_index", 0),
                    "decision": asdict(record.decision),
                    "observation": (
                        asdict(record.observation) if record.observation else None
                    ),
                }
                for record in self.records
            ],
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
    r"(?:\b(?:create|generate|build|make|export|produce|code|develop|design)\b.{0,50}"
    r"\b(?:pdf|xlsx|spreadsheet|docx|document|html|report|artifact|file|website|webpage|site|landing|landing\s+page|prototype|app|application|dashboard|component)\b"
    r"|\.pdf\b|\.xlsx\b|\.docx\b|\.html?\b|\blanding\s+page\b|\bweb\s+app\b|\breact\b|\bvite\b)",
    re.IGNORECASE,
)
_TASK_STATE_METADATA_KEYS = frozenset({"task_type", "stage", "review_status"})


def looks_like_worker_envelope(text: str | None) -> bool:
    """Return True when *text* is a serialized worker/tool result envelope.

    The planner sometimes echoes ``_parse_worker_result`` JSON as a text part.
    That shape must never be promoted to a user-facing final answer.
    """
    raw = str(text or "").strip()
    if not raw or raw[0] != "{" or raw[-1] != "}":
        return False
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if "status" not in payload or "summary" not in payload:
        return False
    return any(
        key in payload
        for key in ("evidence", "artifacts", "remaining_work", "retryable", "sources")
    )


def verify_completion(
    *,
    request: str,
    final_response: str | None,
    ledger: ActionLedger,
) -> CompletionVerification:
    """Verify task completion from observable runtime evidence."""
    response = str(final_response or "").strip()
    # #region agent log
    try:
        import json as _dbg_json
        from pathlib import Path as _DbgPath
        _arts = ledger.artifacts()
        _tools = [str(getattr(r.decision, "action", "") or "") for r in ledger.records[-16:]]
        _DbgPath(r"C:\Users\nanda\OneDrive\Desktop\co-computer\debug-2a93a8.log").open("a", encoding="utf-8").write(_dbg_json.dumps({"sessionId":"2a93a8","hypothesisId":"B","location":"control_loop.py:verify_completion:entry","message":"verify inputs","data":{"request":str(request or "")[:180],"artifact_regex":bool(_ARTIFACT_REQUEST.search(str(request or ""))),"n_artifacts":len(_arts),"artifact_kinds":[str((a or {}).get("kind") or (a or {}).get("title") or "")[:40] for a in _arts[:6]],"tools":_tools,"response_len":len(response),"htmlish":("<" in response and ("class=" in response or "<section" in response.lower())),"response_prefix":response[:120]},"timestamp":int(__import__("time").time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    if not response or looks_like_worker_envelope(response):
        return CompletionVerification(
            verified=False,
            status="failed",
            method="final_response",
            summary=(
                "The model ended without a final response."
                if not response
                else "The model returned a raw tool/worker result instead of a final response."
            ),
            error_code="MISSING_FINAL_RESPONSE",
            remaining_work=["Produce a final response grounded in tool evidence."],
            retryable=True,
        )

    failures = [
        failure
        for failure in ledger.latest_unresolved_failures()
        if failure.error_code not in SKIPPABLE_ERROR_CODES
    ]
    if failures:
        # #region agent log
        try:
            import json as _dbg_json
            from pathlib import Path as _DbgPath
            _DbgPath(r"C:\Users\nanda\OneDrive\Desktop\co-computer\debug-2a93a8.log").open("a", encoding="utf-8").write(_dbg_json.dumps({"sessionId":"2a93a8","hypothesisId":"A","location":"control_loop.py:verify_completion","message":"unresolved failures block completion","data":{"tools":[{"tool":f.tool,"status":f.status,"error_code":f.error_code,"retryable":f.retryable,"remaining":f.remaining_work[:2]} for f in failures[:6]]},"timestamp":int(__import__("time").time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
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
        # #region agent log
        try:
            import json as _dbg_json
            from pathlib import Path as _DbgPath
            _DbgPath(r"C:\Users\nanda\OneDrive\Desktop\co-computer\debug-2a93a8.log").open("a", encoding="utf-8").write(_dbg_json.dumps({"sessionId":"2a93a8","hypothesisId":"B","location":"control_loop.py:verify_completion:missing_artifact","message":"MISSING_ARTIFACT branch","data":{"request":str(request or "")[:180]},"timestamp":int(__import__("time").time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
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
        sources = ledger.all_sources()
        if not sources:
            return CompletionVerification(
                verified=False,
                status="failed",
                method="source_result",
                summary="Research completion requires gathered source evidence.",
                error_code="MISSING_SOURCE_EVIDENCE",
                remaining_work=[
                    "Gather sources with web_search, tavily_search, "
                    "scrape_web_page, or search_sources before answering."
                ],
                retryable=True,
            )
        cited = bool(re.search(r"https?://", response)) or any(
            (source.get("citation_key") and source["citation_key"] in response)
            or (source.get("url") and source["url"] in response)
            for source in sources
        )
        if not cited:
            return CompletionVerification(
                verified=False,
                status="failed",
                method="source_result",
                summary="Sources were gathered but the final response does not cite them.",
                error_code="MISSING_FINAL_CITATIONS",
                evidence=[
                    str(source.get("url") or source.get("citation_key"))
                    for source in sources[:4]
                    if source.get("url") or source.get("citation_key")
                ],
                remaining_work=[
                    "Cite the gathered sources (URLs) inline in the final response."
                ],
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
