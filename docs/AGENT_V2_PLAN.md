# CoComputer Agent V2 — Final Architecture Plan

> **Status: partially superseded (2026-07-09).**
> Fast path (ask/chat/search/current/clarify/capability) and the artifact
> mini-agent were removed in the full-agent-only migration. Every user turn
> now goes through the single planner. See
> [`FULL_AGENT_ONLY_MIGRATION_PLAN.md`](FULL_AGENT_ONLY_MIGRATION_PLAN.md) for
> the current architecture. §2 (target architecture), §4.7–4.8 (fast-path
> cost controls), §6 Phase A step 3 (artifact mini-agent), and §8 (artifact
> mini-agent success criterion) below are retained for historical context
> only — do not implement them.

Status: approved for implementation (historical)
Date: 2026-07-07
ADK version: 1.28.0 (verified: `AgentTool`, `LoopAgent`, `SequentialAgent`, `ParallelAgent`, transfer-disable flags all present)

---

## 1. Goals and constraints

Goals:
- Stop lazy `transfer_to_agent` behavior (control handoffs that never return, token burn, failed simple tasks).
- Make simple tasks (calculators, HTML tools, lookups) complete in the main agent without sandbox, workspace, or delegation.
- Add human-in-the-loop (`ask_user`).
- Enforce budgets in code, not prompts.
- Production-capable foundation for a startup product.

Constraints:
- Models: Qwen (DashScope) only for now. Qwen 3.7-max / 3.6-plus / 3.6-flash tiers.
- Gemini/Vertex infrastructure stays in code, dormant, switchable by config. DO NOT delete.
- GCP budget: $100 credits. Free-tier services only. No Memorystore, no Agent Engine.
- Framework: keep Google ADK. No rewrite to another framework.

Evidence for the core change (ADK docs + Google Cloud blog):
- `sub_agents` = LLM-driven transfer; child owns conversation; known production "stickiness" gotcha (child never transfers back). This is exactly the observed bug.
- `AgentTool` = explicit invocation; child runs isolated, returns result; control returns to parent structurally guaranteed.
- Google guidance: tools for discrete stateless work, sub_agents only for multi-turn conversational children. Our specialists do discrete work → AgentTool is correct.

---

## 2. Target architecture

```
User message
  │
  ▼
handle_text_input / handle_user_utterance
  │
  ▼
PLANNER (single loop agent) — EVERY turn
  model: planner_model (qwen3.6-max-preview)
  NO sub_agents list → transfer_to_agent cannot exist
  NO fast path, NO artifact mini-agent
  Self-triage: tools? evidence? deliverable? skills?
  loop: plan → act (tool call) → observe → re-plan → done
  max turns: max_agent_turns (30); optional Phase B budget hint later

  direct tools:
    prepare_task_workspace, initialize_task_state, update_task_state,
    read_task_state, write_todo_list, update_todo_item,
    write_workspace_file, read_workspace_file, list_workspace_files,
    web_search, scrape_web_page, tavily_search, search_sources,
    publish_html_artifact, render_ui, read_skill,
    ask_user, request_background_task, remember_fact, recall_facts
    [connector tools injected ONLY when user has them connected/selected]

  worker tools:
    AgentTool(terminal_worker, skip_summarization=True)  # PDF/xlsx/docx/shell
    AgentTool(desktop_worker,  skip_summarization=True)  # GUI/browser

  background parallelism (subagents.py):
    invoke_subagent / send_message / get_subagent_result /
    list_subagents / cancel_subagent / await_subagents

See docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md for the migration that removed
the fast path and artifact mini-agent.
```

### Workers (foreground, sequential, sandbox-owning)

Split by TOOL SURFACE, not persona. Rule: worker ≤ ~12 tools.

**terminal_worker** — model qwen3.6-plus
- run_command, write_workspace_file, read_workspace_file, list_workspace_files,
  extract_pdf_text, generate_pdf_report, generate_excel_report, generate_docx_report,
  save_as_artifact, read_skill (~10 tools)
- No GUI tools → structurally cannot screenshot-spam.

**desktop_worker** — model qwen3.7-plus (visual work needs stronger model)
- take_screenshot, left_click, right_click, double_click, move_mouse, drag,
  type_text, press_key, scroll_screen, open_browser,
  playwright_navigate, playwright_click, playwright_type, playwright_get_text,
  playwright_wait_for, read_skill (~16 tools; trim playwright_* if misroutes appear)
- No run_command.

### Background subagent types (parallel, cheap — model qwen3.6-flash)

Existing `SubagentSupervisor._tools_for_type` in `subagents.py`, updated surfaces:
- researcher: web_search, scrape_web_page, tavily_search, write_workspace_file, read_skill
- coder: run_command, write_workspace_file, read_workspace_file, list_workspace_files, read_skill
- writer: write_workspace_file, read_workspace_file, publish_html_artifact, read_skill

### Deep research route

No deepresearcher persona. Route `deep` = planner + background researcher subagents (fan-out)
+ optional review pass: `LoopAgent(name="review_loop", max_iterations=2,
sub_agents=[draft_agent, reviewer_agent, CheckAndEscalate])` wrapped as AgentTool,
used only when route=deep. `create_deepresearcher_agent` code stays parked (dormant,
like Gemini infra), not deleted.

### Skills

Two layers, both kept:
1. Static: enabled-skills prompt injection (`skill_instruction` param — already wired everywhere).
2. Dynamic: `read_skill` tool on planner, both workers, all three background types.

---

## 3. Model strategy

New helper (single place): `nexus/model_select.py`

```python
def create_model(role: str):  # role: "planner" | "worker" | "worker_visual" | "micro" | "router"
    # reads settings.model_provider: "qwen" (default now) | "gemini"
    # qwen:   planner=qwen3.7-max, worker=qwen3.6-plus, worker_visual=qwen3.7-plus,
    #         micro=qwen3.6-flash, router=qwen3-4b
    # gemini: maps to runtime_config.gemini_agent_model / light model (dormant path, kept working)
```

- All `_get_model()` functions in `agent.py`, `agents/orchestrator_agent.py`, `agents/sub_agents.py`,
  `subagents.py` call `create_model(role)`.
- Gemini/Vertex code paths untouched and switchable via `model_provider` setting.
- DashScope implicit context caching is automatic — no code needed; benefit grows with
  stable prompt prefixes (keep system prompts stable across turns).

---

## 4. Token and cost controls (code-enforced)

1. `skip_summarization=True` on all AgentTools — removes one LLM call per worker invocation.
2. Workers receive compact task briefs (AgentTool isolation), not full history.
3. Planner prompt rewritten: ~170 lines → ~60. Routing-policy essay deleted (no transfer decisions exist anymore). Keep: decision gate, workspace rules, tool hints, safety.
4. Planner tool surface ≤ 15 + 2 AgentTools. Connector tools injected only when connected.
5. Per-route turn caps enforced in `run_agent_turn` (pass `max_turns` param): artifact 6, work 20, deep 30.
6. Per-turn worker-call cap: max 4 AgentTool invocations per user turn (enforce in `tool_gateway` counter, structured error on breach).
7. ~~Fast path (no agent) for ask/chat/search/current — exists, keep strict.~~ **Removed 2026-07-09** — every turn now goes through the planner (see `FULL_AGENT_ONLY_MIGRATION_PLAN.md`).
8. Lazy sandbox boot — exists, keep. E2B credit-burn protection now relies solely on lazy boot inside `_prepare_workspace_for_turn` (artifact route no longer exists).

---

## 5. GCP $100 budget map

| Service | Decision | Note |
|---|---|---|
| Cloud Run (FE+BE) | keep, free tier | scale-to-zero |
| Firestore | keep, free tier | 20K writes/day cap → batch step writes, downsample `agent_thinking` persistence |
| GCS | keep, 5GB free | artifacts |
| Cloud Tasks | keep, 1M ops free | durable queue |
| Secret Manager | keep, 6 versions free | |
| BigQuery | optional later | eval + cost analytics, free tier 10GB/1TB |
| Memorystore Redis | SKIP (~$35/mo) | in-proc asyncio locks (exists) + Firestore lease docs for durable locks |
| Vertex AI / Agent Engine | DORMANT | wired, unused until quota/budget OK |

Main real spend: DashScope tokens + E2B sandbox hours. Controls in §4 target exactly these.

---

## 6. Migration phases

### Phase A — core rebuild (2–3 days)
Files: `nexus/model_select.py` (new), `nexus/agent.py`, `nexus/agents/orchestrator_agent.py`,
`nexus/agents/sub_agents.py`, `nexus/orchestrator.py`, `nexus/tools/ask_user.py` (new),
`nexus/tool_gateway.py`, `nexus/subagents.py`, `nexus/config.py`

1. `create_model(role)` + `model_provider` setting. All `_get_model` call it.
2. `create_planner_agent()` in `agent.py`:
   - terminal_worker + desktop_worker as `AgentTool(..., skip_summarization=True)`
   - no `sub_agents` param
   - new ~60-line planner prompt
   - keep `create_multi_agent` behind `use_multi_agent` flag for rollback
3. ~~Artifact mini-agent: `create_artifact_agent()`; orchestrator builds it when route=artifact~~ **Removed 2026-07-09** — the planner has `publish_html_artifact` + `render_ui` directly and self-triages HTML deliverables without booting a workspace. `FULL_AGENT_ONLY_MIGRATION_PLAN.md` §5.
4. `ask_user(question)` tool: emits WS `user_question` event, pauses via future (copy
   permission-card flow), frontend question card in chat, response resumes run.
5. Budgets: per-route `max_turns` in `run_agent_turn`; worker-call counter in gateway.
6. Background subagent types updated (researcher/coder/writer surfaces + flash model + read_skill).

### Phase B — verification (1–2 days)
7. Update `test_agent_routing.py` to 2-worker shape; add budget tests; run full `pytest agent/tests`.
8. Eval harness with `adk eval` (free, built-in): 25–40 canned tasks
   (calculator artifact, news lookup, Gmail read, repo fix, GUI click, research).
   Metrics: success, worker calls, tokens, latency. This gates every later change.
9. Manual smoke: calculator HTML artifact; research + parallel subagents; Outputs tab + run steps.
10. Firestore write batching for run steps (free-tier guard).

### Phase C — durability (1–2 weeks, prior plan unchanged)
11. Durable subagents V2: persist `SubagentRecord` to Firestore, restart recovery,
    parent-run reconciliation, cancel/resume correctness.
12. Locks: per-file write locks, per-port/dev-server ownership (in-proc + Firestore lease),
    clear conflict errors.
13. Subagent activity UI polish: grouped steps under parent run, cancel button, progress states.

### Phase D — structural refactor (only after evals green)
14. Split `NexusOrchestrator` → AgentRuntime / RunRecorder / WorkspaceCoordinator / VoiceRuntime
    (SubagentSupervisor exists). Freeze WS event contract during split.
15. Split `FirestoreHistoryRepository` by domain (sessions/messages/runs/artifacts/settings).

### Phase E — startup hardening
16. Observability: per-run trace IDs, cost-per-run dashboard, Sentry alerts.
17. Billing: credits → Stripe metering, hard per-user budget cutoffs.
18. Staging env + post-deploy smoke; SLOs (p95 first-token, eval success rate).
19. Security pass: firestore.rules audit, sandbox egress, BYOK secret handling.
20. React/Next sandbox preview with dev-server lifecycle (uses Phase C port locks).

---

## 7. Rollback

- `use_multi_agent=True` setting restores old transfer-mesh `create_multi_agent`.
- `model_provider="gemini"` restores Gemini instantly.
- Deepresearcher + old sub-agent factories parked, not deleted.
- WS event contract unchanged in Phases A–C → frontend safe.

---

## 8. Success criteria (Phase A/B exit)

- "Create a simple calculator" → planner self-triage → publish_html_artifact → done in a few turns, 0 workers, 0 sandbox boots (artifact mini-agent removed 2026-07-09).
- "Fix bug in repo X" → planner → terminal_worker call(s) → result returns to planner → synthesis.
- No `transfer_to_agent` anywhere in new path (tool cannot exist).
- Agent asks a question via ask_user when input genuinely missing.
- Full pytest green + eval suite ≥ 80% task success.
- Token per simple task down ≥ 60% vs current (measure via usage records).

---

## 9. Production eval ownership and release policy

The repository-owned production suite is the source of truth:

- Catalog: `agent/nexus/eval/task_cases.py` (exactly 25 user tasks).
- Scoring and regression policy: `agent/nexus/eval/production_suite.py`.
- CLI: `python -m nexus.eval.run_task_eval`.
- Reports: `agent/reports/` in CI artifacts; durable live baselines live under
  `agent/nexus/eval/baselines/`.
- Owner: the agent-runtime maintainers. Changes to a prompt, expected state,
  scoring rule, or critical-task designation require the same review as an
  agent runtime change.

Local commands from `agent/`:

```bash
uv sync --locked --extra dev
uv run python -m nexus.eval.run_task_eval validate
uv run pytest tests/test_adk_compatibility.py tests/test_production_eval.py -q
uv run python -m nexus.eval.run_task_eval live nexus.eval.live_executor:execute \
  --output reports/candidate.json
uv run python -m nexus.eval.run_task_eval gate \
  nexus/eval/baselines/live.json reports/candidate.json \
  --output reports/release-gate.json
```

The checked-in `contract.json` only proves catalog/scorer conformance. It is
explicitly rejected as a release candidate. A release baseline must be a live
run against the staging agent and pinned fixture accounts. Fixture metadata is
tracked in `agent/nexus/eval/fixtures/manifest.json`.

Initial quality thresholds are derived from the first accepted live baseline,
not hand-picked. The gate blocks any regression in overall success, critical
success, required tool order, or safety. It also blocks a previously passing
critical case that fails in the candidate. Latency, token usage, and cost are
recorded; increases above 25% are warnings until enough live baselines exist to
set stable service-level gates. Baseline promotion requires human review of all
failed cases and traces. The prior baseline is retained as a CI artifact.
