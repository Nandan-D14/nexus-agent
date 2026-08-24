# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""ADK 2 Workflow-as-Tool pilot for deterministic deep research.

The graph uses model-free function nodes. It adds no conversational personas:
the foreground Qwen planner remains the only decision-making agent.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from google.adk.workflow import FunctionNode, JoinNode, START, Workflow
from pydantic import BaseModel, ConfigDict, Field

from nexus.config import settings
from nexus.tools.docs import publish_html_artifact
from nexus.tools.web import scrape_web_page, web_search
from nexus.tools.workspace import write_workspace_file


class DeepResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(
        min_length=8,
        max_length=4000,
        description="Explicit multi-source research or report request.",
    )


class SearchCandidate(BaseModel):
    title: str
    url: str
    snippet: str = ""


class SearchBranch(BaseModel):
    query: str
    status: str
    summary: str
    results: list[SearchCandidate] = Field(default_factory=list)


class VerifiedSource(BaseModel):
    title: str
    url: str
    domain: str
    snippet: str = ""
    content: str = ""
    verification: str
    saved_path: str = ""
    verification_summary: str = ""


class EvidenceBundle(BaseModel):
    request: str
    sources: list[VerifiedSource]
    search_errors: list[str]


class DraftReport(BaseModel):
    request: str
    sources: list[VerifiedSource]
    report: str
    search_errors: list[str]


class ReviewedReport(BaseModel):
    request: str
    sources: list[VerifiedSource]
    report: str
    review_status: str
    review_issues: list[str]
    domain_count: int
    accessible_count: int


class DeepResearchWorkflowResult(BaseModel):
    status: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)
    retryable: bool = False
    error_code: str = ""
    review: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, str]] = Field(default_factory=list)
    report: str = ""


def _metadata(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    value = result.get("metadata")
    return dict(value) if isinstance(value, dict) else {}


def _safe_public_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return ""
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return raw
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    ):
        return ""
    return raw


def _slug(value: str) -> str:
    return (
        re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]
        or "deep-research"
    )


async def _search_branch(
    request: str,
    suffix: str,
) -> SearchBranch:
    query = " ".join(f"{request} {suffix}".split())
    result = await web_search(query=query, max_results=5)
    metadata = _metadata(result)
    candidates = []
    for item in metadata.get("results", [])[:5]:
        if not isinstance(item, dict):
            continue
        candidates.append(
            SearchCandidate(
                title=str(item.get("title") or item.get("url") or "Source")[
                    :300
                ],
                url=str(item.get("url") or "")[:2000],
                snippet=str(item.get("snippet") or "")[:1500],
            )
        )
    return SearchBranch(
        query=query,
        status=(
            str(result.get("status") or "error")
            if isinstance(result, dict)
            else "error"
        ),
        summary=(
            str(result.get("summary") or "")
            if isinstance(result, dict)
            else str(result)
        )[:1000],
        results=candidates,
    )


async def search_primary(
    request: str,
) -> SearchBranch:
    """Run the primary bounded search branch."""
    return await _search_branch(request, "")


async def search_evidence(
    request: str,
) -> SearchBranch:
    """Run the evidence-oriented bounded search branch."""
    return await _search_branch(request, "evidence sources")


async def search_counterpoints(
    request: str,
) -> SearchBranch:
    """Run the limitations and alternatives bounded search branch."""
    return await _search_branch(
        request,
        "limitations alternatives criticism",
    )


async def verify_sources(
    node_input: dict[str, SearchBranch],
) -> EvidenceBundle:
    """Deduplicate public URLs and capture bounded readable evidence."""
    branches = list(node_input.values())
    request = ""
    candidates: list[SearchCandidate] = []
    search_errors: list[str] = []
    seen_urls: set[str] = set()
    for branch in branches:
        if not request:
            for suffix in (
                " limitations alternatives criticism",
                " evidence sources",
            ):
                if branch.query.endswith(suffix):
                    request = branch.query[: -len(suffix)].strip()
                    break
            request = request or branch.query
        if branch.status != "success":
            search_errors.append(branch.summary)
        for candidate in branch.results:
            url = _safe_public_url(candidate.url)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(candidate.model_copy(update={"url": url}))

    source_limit = max(
        3,
        min(12, int(settings.deep_research_workflow_max_sources)),
    )
    selected = candidates[:source_limit]
    semaphore = asyncio.Semaphore(3)

    async def capture(
        index: int,
        candidate: SearchCandidate,
    ) -> VerifiedSource:
        async with semaphore:
            result = await scrape_web_page(
                url=candidate.url,
                output_basename=f"workflow-source-{index + 1}",
            )
        metadata = _metadata(result)
        success = (
            isinstance(result, dict)
            and result.get("status") == "success"
        )
        return VerifiedSource(
            title=candidate.title,
            url=candidate.url,
            domain=(urlparse(candidate.url).hostname or "").lower(),
            snippet=candidate.snippet,
            content=str(metadata.get("content") or "")[:5000],
            verification="accessible" if success else "search_only",
            saved_path=str(metadata.get("saved_path") or ""),
            verification_summary=(
                str(result.get("summary") or "")
                if isinstance(result, dict)
                else str(result)
            )[:1000],
        )

    sources = (
        await asyncio.gather(
            *[
                capture(index, candidate)
                for index, candidate in enumerate(selected)
            ]
        )
        if selected
        else []
    )
    return EvidenceBundle(
        request=request,
        sources=sources,
        search_errors=search_errors,
    )


def synthesize_evidence(
    node_input: EvidenceBundle,
) -> DraftReport:
    """Assemble a citation-indexed evidence report for Qwen synthesis."""
    lines = [
        f"# Deep research evidence report: {node_input.request}",
        "",
        "## Method",
        (
            "Three deterministic search branches were deduplicated, public "
            "URLs were checked, and accessible pages were captured."
        ),
        "",
        "## Evidence",
    ]
    for index, source in enumerate(node_input.sources, start=1):
        content = (source.content or source.snippet).strip()
        excerpt = " ".join(content.split())[:1800]
        lines.extend(
            [
                f"### {index}. {source.title} [{index}]",
                "",
                excerpt or "No readable excerpt was available.",
                "",
            ]
        )
    lines.extend(["## Sources", ""])
    for index, source in enumerate(node_input.sources, start=1):
        lines.append(
            f"[{index}] {source.title} — {source.url} "
            f"({source.verification})"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            (
                "This deterministic pilot assembles reviewed evidence. The "
                "foreground Qwen planner remains responsible for semantic "
                "conclusions and recommendations."
            ),
        ]
    )
    return DraftReport(
        request=node_input.request,
        sources=node_input.sources,
        report="\n".join(lines).strip()[:40_000],
        search_errors=node_input.search_errors,
    )


def review_report(
    node_input: DraftReport,
) -> ReviewedReport:
    """Apply deterministic source-diversity and citation release checks."""
    domains = {
        source.domain for source in node_input.sources if source.domain
    }
    accessible_count = sum(
        source.verification == "accessible"
        for source in node_input.sources
    )
    issues = []
    if len(node_input.sources) < 3:
        issues.append("At least three distinct sources are required.")
    if len(domains) < 2:
        issues.append("At least two source domains are required.")
    if accessible_count < 1:
        issues.append("At least one source must be directly accessible.")
    missing = [
        index
        for index in range(1, len(node_input.sources) + 1)
        if f"[{index}]" not in node_input.report
    ]
    if missing:
        issues.append(
            "Missing citation markers: "
            + ", ".join(str(index) for index in missing)
        )
    return ReviewedReport(
        request=node_input.request,
        sources=node_input.sources,
        report=node_input.report,
        review_status="passed" if not issues else "changes_requested",
        review_issues=issues,
        domain_count=len(domains),
        accessible_count=accessible_count,
    )


async def publish_report(
    node_input: ReviewedReport,
) -> DeepResearchWorkflowResult:
    """Publish only reports that pass deterministic review."""
    review = {
        "status": node_input.review_status,
        "issues": node_input.review_issues,
        "source_count": len(node_input.sources),
        "domain_count": node_input.domain_count,
        "accessible_count": node_input.accessible_count,
    }
    if node_input.review_status != "passed":
        return DeepResearchWorkflowResult(
            status="partial",
            summary="Deep research review did not pass.",
            evidence=node_input.review_issues[:10],
            remaining_work=[
                "Gather additional accessible, diverse sources and rerun."
            ],
            retryable=True,
            error_code="DEEP_RESEARCH_REVIEW_FAILED",
            review=review,
        )

    filename = f"deep-research-{_slug(node_input.request)}.md"
    relative_path = f"outputs/{filename}"
    await write_workspace_file(relative_path, node_input.report)
    html_report = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font:16px/1.55 system-ui;max-width:980px;"
        "margin:40px auto;padding:0 24px;white-space:pre-wrap}"
        "a{color:#2563eb}</style></head><body>"
        f"{html.escape(node_input.report)}</body></html>"
    )
    publish_result = await publish_html_artifact(
        title=f"Deep research: {node_input.request[:100]}",
        html=html_report,
        filename=filename.replace(".md", ".html"),
    )
    artifacts: list[dict[str, Any]] = [
        {"path": relative_path, "kind": "markdown"}
    ]
    publish_metadata = _metadata(publish_result)
    if (
        isinstance(publish_result, dict)
        and publish_result.get("status") == "success"
    ):
        artifacts.append(
            {
                "path": str(publish_metadata.get("path") or ""),
                "url": str(publish_metadata.get("url") or ""),
                "artifact_id": str(
                    publish_metadata.get("artifact_id") or ""
                ),
                "kind": "html",
            }
        )
    return DeepResearchWorkflowResult(
        status="success",
        summary=(
            f"Deep research workflow published {len(node_input.sources)} "
            "reviewed sources."
        ),
        evidence=[
            f"{len(node_input.sources)} sources",
            f"{node_input.domain_count} domains",
            f"{node_input.accessible_count} accessible pages",
        ],
        artifacts=artifacts,
        review=review,
        sources=[
            {
                "title": source.title,
                "url": source.url,
                "verification": source.verification,
            }
            for source in node_input.sources
        ],
        report=node_input.report,
    )


def create_deep_research_workflow() -> Workflow:
    """Build fan-out → verify → synthesize → review → publish graph."""
    primary = FunctionNode(
        func=search_primary,
        name="research_query_primary",
        parameter_binding="node_input",
        timeout=30,
    )
    evidence = FunctionNode(
        func=search_evidence,
        name="research_query_evidence",
        parameter_binding="node_input",
        timeout=30,
    )
    counterpoints = FunctionNode(
        func=search_counterpoints,
        name="research_query_counterpoints",
        parameter_binding="node_input",
        timeout=30,
    )
    join = JoinNode(
        name="research_fan_in",
        description="Wait for all bounded search branches.",
    )
    verification = FunctionNode(
        func=verify_sources,
        name="source_verification",
        parameter_binding="state",
        timeout=60,
    )
    synthesis = FunctionNode(
        func=synthesize_evidence,
        name="evidence_synthesis",
        parameter_binding="state",
    )
    review = FunctionNode(
        func=review_report,
        name="report_review",
        parameter_binding="state",
    )
    publication = FunctionNode(
        func=publish_report,
        name="report_publish",
        parameter_binding="state",
        timeout=60,
    )
    return Workflow(
        name="deep_research_workflow",
        description=(
            "Use only for explicit multi-source deep research or report "
            "requests. Runs deterministic fan-out, source verification, "
            "evidence synthesis, review, and publishing."
        ),
        input_schema=DeepResearchRequest,
        output_schema=DeepResearchWorkflowResult,
        edges=[
            (
                START,
                (primary, evidence, counterpoints),
                join,
                verification,
                synthesis,
                review,
                publication,
            )
        ],
        max_concurrency=3,
        timeout=180,
    )


def create_deep_research_workflow_tool() -> Workflow:
    """Return the Workflow; ADK converts BaseNode tools to NodeTool."""
    return create_deep_research_workflow()


__all__ = [
    "DeepResearchRequest",
    "DeepResearchWorkflowResult",
    "create_deep_research_workflow",
    "create_deep_research_workflow_tool",
]
