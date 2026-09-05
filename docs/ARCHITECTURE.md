# Co-Computer Architecture (Mermaid + Plain Text)

## 1) Diagram (No Mermaid Required)

```text
                            +--------------------------------------+
                            |             User Browser             |
                            |     Next.js UI + mic + speaker       |
                            +------------------+-------------------+
                                               |
                                   HTTPS + WebSocket
                                               |
                          +--------------------v--------------------+
                          |      Frontend Service (Cloud Run)       |
                          |             nexus-frontend              |
                          +--------------------+--------------------+
                                               |
                                  /api/* proxy route
                                  frontend/src/app/api/[...path]/route.ts
                                               |
                          +--------------------v--------------------+
                          |       Agent Service (FastAPI)           |
                          |            nexus-agent                  |
                          |      REST + /ws/{session_id}           |
                          +--------------------+--------------------+
                                               |
      +------------------------+---------------+--------------+------------------------+
      |                        |                              |                        |
+-----v------+        +--------v---------+            +-------v--------+      +--------v--------+
| Auth Layer |        | Session Manager  |            | History Repo   |      | Runtime Config  |
| Firebase   |        | session.py       |            | Firestore      |      | BYOK / provider |
+------------+        +--------+---------+            +-------+--------+      +--------+--------+
                                |                              |                        |
                                |                              |                        |
                       +--------v---------+            +-------v--------+      +--------v--------+
                       | E2B Sandbox      |            | Firestore DB   |      | Secret Manager  |
                       | Linux desktop    |            | user/session   |      | runtime secrets |
                       +--------+---------+            +----------------+      +-----------------+
                                |
                                | tool calls
                                v
                    +------------------------------+
                    | Agent Tools                  |
                    | browser / computer / bash /  |
                    | take_screenshot / bg_task    |
                    +---------------+--------------+
                                    |
                                    | reasoning + multimodal
                                    v
                    +------------------------------+
                    | Gemini via Google GenAI SDK  |
                    | - Live model (voice stream)  |
                    | - Vision model (screenshots) |
                    | - Tool-calling orchestration |
                    +------------------------------+
```

## 2) How Agent and Gemini Work Together

### A. Text/Command path
1. User sends text from frontend over WebSocket.
2. `nexus.orchestrator.NexusOrchestrator` receives it.
3. Orchestrator runs the single Qwen planner (`nexus_planner`) with terminal/desktop AgentTool workers.
4. The planner decides tool calls; workers return typed evidence to the planner.
5. Tools execute inside E2B sandbox (`bash`, mouse/keyboard, Chromium CDP/Playwright, screenshot).
6. Tool results are fed back for the next reasoning step.
7. Final response is streamed to frontend after completion verification.

### B. Voice path (Gemini Live)
1. Frontend streams mic PCM audio to backend WebSocket.
2. `GeminiLiveManager` opens `client.aio.live.connect(...)`.
3. Live returns:
   - user transcript
   - model transcript
   - audio response
   - optional tool calls
4. Backend forwards transcripts/audio events to frontend and executes any tool calls.

### C. Vision path (Screenshot understanding)
1. Tool `take_screenshot` captures E2B screen.
2. JPEG bytes are sent to the Qwen vision provider (`vision_provider.py`).
3. Structured screen observations are returned to the planner/desktop worker.
4. Agent uses that perception to decide next UI action.
5. If rate-limited, configured Qwen vision fallback tiers are tried and traced.

## 3) Key Files
- `agent/nexus/orchestrator.py` - session-level control loop (voice + agent + tools).
- `agent/nexus/agents/planner_agent.py` - single production planner and AgentTool workers.
- `agent/nexus/voice.py` - Gemini Live bidirectional audio session manager.
- `agent/nexus/vision_provider.py` - Qwen screenshot grounding.
- `agent/nexus/tools/*.py` - executable actions in sandbox.
- `frontend/src/app/api/[...path]/route.ts` - frontend API proxy to backend.
- `deploy/gcp/deploy.sh` - Cloud Build + Artifact Registry + Cloud Run deployment flow.

## 4) Artifact Durability (Manus-style - all file types)

Sandboxes (E2B) are ephemeral execution only: idle pause ~5m
(`idle_sandbox_pause_seconds`), destroy ~120m (`session_timeout_minutes`).
Delivered files (xlsx/csv/pdf/docx/pptx/html/md/images) are permanent:

- Create: `tools/docs.py` pre-generates `artifact_id`, uploads immutable bytes
  to GCS `nexus-artifacts-{env}/{session}/{run}/{artifact_id}/{file}`
  (`storage.py:artifact_blob_name_for`), then writes Firestore doc with
  `gcs_bucket/gcs_blob/relative_path`. Upload failure ->
  `ARTIFACT_PERSISTENCE_FAILED`, never a sandbox-only deliverable.
- Serve: `GET /artifacts/{id}/content` (same-origin proxy, no CORS) and
  `/artifacts/{id}/download` (fresh 1h signed URL) try stored > immutable >
  legacy blobs. `GET /sessions/{id}/files/download` is live-only (410
  `SANDBOX_EPHEMERAL` with hint to durable API).
- Read: `history_repository._get_artifact_for_owner_sync` tries session doc,
  then `users/{owner}/tasks/...` mirrors, then collection-group
  (`firestore.indexes.json` must be deployed). Never gates on parent session.
- Frontend: `artifact-url.ts:resolveArtifactUrl` is durable-first,
  `allowSandbox=false` by default. Sheets/CSVs parse in-browser via `xlsx`.
  Office previews use immutable `preview_gcs_blob` siblings.
- See `docs/ARTIFACT_DURABILITY_RUNBOOK.md`.
