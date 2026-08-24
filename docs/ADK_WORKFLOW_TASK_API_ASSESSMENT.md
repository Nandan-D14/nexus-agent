# ADK workflow pilot and Task API assessment

## Workflow-as-Tool pilot

The optional `deep_research_workflow` tool is implemented with the ADK 2.4.0
`Workflow` graph API, parallel `FunctionNode` branches, `JoinNode`, and
model-free typed stages. ADK exposes the graph to the planner as a long-running
`NodeTool`.

Its fixed pipeline is:

1. three bounded search branches in parallel;
2. public-URL validation, deduplication, and source capture;
3. citation-indexed evidence synthesis;
4. deterministic source-diversity and citation review;
5. Markdown/HTML publication only after review passes.

This does not introduce another model persona. The Qwen planner remains the
only foreground decision-maker and consumes the workflow's typed result before
forming conclusions. Normal chat, browser interaction, and GUI control remain
on the typed planner/controller loop.

The pilot is off by default. Enable it with:

```text
DEEP_RESEARCH_WORKFLOW_ENABLED=true
```

Run its conformance tests with:

```bash
uv run pytest tests/test_adk_workflow_pilot.py -q
```

Promotion requires green deep-research eval cases with no safety regression.

## ADK Task API decision

Decision: **defer migration**.

The pinned `google-adk==2.4.0` package exposes graph workflows, resumable node
events, and in-session `LlmAgent(mode="task")` delegation. The task package
does not export a public lifecycle contract, and task-mode agents cannot be
static Workflow graph nodes in this release. ADK does not expose a public
`google.adk.tasks`, `google.adk.task`, or `google.adk.task_api` lifecycle
surface with Task and TaskService/TaskManager contracts.

CoComputer therefore retains its repository-owned Firestore runs, Cloud Tasks
dispatch, leases, claim generations, approval resume, checkpoints, budgets,
and stale-run recovery. `nexus.adk_capabilities.assess_adk_task_api()` is a
conformance probe that fails the pinned expectation when a future ADK upgrade
introduces a candidate public API.

Before migration, a future API must prove:

- durable state survives process and region restart;
- claims and side effects remain exactly-once or idempotent;
- approval state resumes the exact blocked action;
- budgets, tracing, final verification, and subagent checkpoints are retained;
- current production-task records can be migrated or read through an adapter;
- two release baselines and canary runs show no success or safety regression.
