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
3. Orchestrator runs ADK multi-agent flow (`nexus_orchestrator` + sub-agents).
4. Model (`CredentialedGemini`) decides tool calls.
5. Tools execute inside E2B sandbox (`bash`, mouse/keyboard, browser, screenshot).
6. Tool results are fed back to Gemini for next reasoning step.
7. Final response is streamed to frontend.

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
2. JPEG bytes are sent to Gemini Vision (`generate_content`).
3. Vision description is returned to the orchestrator.
4. Agent uses that perception to decide next UI action.
5. If rate-limited, configured fallback models are tried.

## 3) Key Files
- `agent/nexus/orchestrator.py` - session-level control loop (voice + agent + tools).
- `agent/nexus/voice.py` - Gemini Live bidirectional audio session manager.
- `agent/nexus/vision.py` - screenshot analysis using Gemini vision models.
- `agent/nexus/credentialed_gemini.py` - per-session Gemini client wrapper.
- `agent/nexus/agents/orchestrator_agent.py` - top-level ADK orchestrator and delegation policy.
- `agent/nexus/tools/*.py` - executable actions in sandbox.
- `frontend/src/app/api/[...path]/route.ts` - frontend API proxy to backend.
- `deploy/gcp/deploy.sh` - Cloud Build + Artifact Registry + Cloud Run deployment flow.
