# CoComputer

Give an agent a real computer.

You talk. It actually does the work — on a real screen, not in a chat bubble.

Each session boots an isolated cloud Linux desktop. Chat sits next to a live desktop. The agent can see the screen, click, type, run the terminal, browse, and use the tools you connect.

Add your own API keys in Settings before using the agent (BYOK).

## What it does

- Isolated Linux desktop per session (E2B sandbox)
- Live screen in the workspace — the agent sees what is on it
- Mouse, keyboard, and terminal — not text-only
- Talk or type in the same session
- Connectors you opt in: Drive, Gmail, GitHub, Linear, Slack, Vercel, MCP, and more
- Your models, your keys — encrypted BYOK, no single-vendor lock-in
- Session history, artifacts, and templates

## Stack

- **Frontend:** Next.js, TypeScript, Tailwind CSS
- **Backend:** FastAPI (Python)
- **Auth & data:** Firebase Auth, Firestore
- **Desktop:** E2B cloud Linux sandboxes (live VNC)
- **Models:** BYOK — Gemini, OpenAI, Anthropic, Qwen, OpenRouter, and custom providers
- **Deploy:** Google Cloud Run

## Local setup

### Prerequisites

- Node.js 20+
- Python 3.11+
- Firebase project (Auth + Firestore)
- [E2B](https://e2b.dev) API key
- At least one model provider key (configured in the app Settings after sign-in)

### Backend

```bash
cd agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env       # fill E2B, Firebase, and encryption keys
uvicorn nexus.server:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local  # AGENT_URL, WebSocket URL, Firebase web config
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), sign in with Google, add keys in Settings, start a session.

## Try it

1. **Desktop** — “Open a browser and search for today’s AI news.” Watch the live screen.
2. **Terminal** — “Create a folder `demo` and a `hello.py` that prints hello, then run it.”
3. **Voice (optional)** — Mic on, “What do you see on the screen right now?”
4. **Connectors** — Connect GitHub or Drive, then ask the agent to use them.

## Architecture

<details>
<summary>System overview</summary>

```mermaid
graph TB
    subgraph CLIENT["Frontend — Next.js"]
        UI["App Shell"]
        CHAT["Chat"]
        DESKTOP["Live desktop"]
        AUTH_CTX["Firebase Auth"]
        WS_HOOK["WebSocket"]
        API_CLIENT["REST client"]
    end

    subgraph FIREBASE_SERVICES["Firebase"]
        FB_AUTH["Authentication"]
        FIRESTORE[("Firestore")]
    end

    subgraph BACKEND["Backend — FastAPI"]
        SERVER["nexus.server"]
        WS_EP["/ws/{session_id}"]
        ORCH["Orchestrator"]
        SANDBOX_MGR["Sandbox manager"]
    end

    subgraph SANDBOX["E2B"]
        E2B["Isolated Linux desktop"]
        VNC_STREAM["VNC stream"]
    end

    AUTH_CTX --> FB_AUTH
    API_CLIENT --> SERVER
    WS_HOOK --> WS_EP
    WS_EP --> ORCH
    ORCH --> SANDBOX_MGR
    SANDBOX_MGR --> E2B
    E2B --> VNC_STREAM
    VNC_STREAM -.-> DESKTOP
    SERVER --> FIRESTORE
```

</details>

<details>
<summary>Full architecture diagrams</summary>

### System Overview

```mermaid
graph TB
    subgraph CLIENT["Frontend — Next.js"]
        UI["App Shell"]
        CHAT["Unified Chat Panel"]
        DESKTOP["Desktop Panel (VNC)"]
        MIC["Mic (PCM)"]
        AUTH_CTX["Auth Context"]
        WS_HOOK["useWebSocket"]
        API_CLIENT["API Client"]
    end

    subgraph FIREBASE_SERVICES["Firebase / Google Cloud"]
        FB_AUTH["Firebase Authentication"]
        FIRESTORE[("Cloud Firestore")]
    end

    subgraph BACKEND["Backend — FastAPI"]
        SERVER["server.py"]
        WS_EP["/ws/{session_id}"]
        WS_HANDLER["ws_handler.py"]
        AUTH_MW["auth.py"]
        SESSION_MGR["session manager"]
        HISTORY_REPO["history repository"]
        RUNTIME_CFG["runtime_config.py"]
        CRYPTO_MOD["crypto.py (BYOK)"]
    end

    subgraph ORCHESTRATION["Orchestration"]
        ORCH["orchestrator.py"]
    end

    subgraph TOOLS["Agent tools"]
        SCREEN_TOOL["screen"]
        COMPUTER_TOOL["mouse / keyboard"]
        BASH_TOOL["bash"]
        BROWSER_TOOL["browser"]
    end

    subgraph SANDBOX["E2B Desktop Sandbox"]
        SANDBOX_MGR["sandbox.py"]
        E2B["Cloud Linux desktop"]
        VNC_STREAM["VNC stream"]
    end

    AUTH_CTX -->|"ID token"| FB_AUTH
    API_CLIENT -->|"REST"| SERVER
    WS_HOOK -->|"WebSocket"| WS_EP
    SERVER --> AUTH_MW
    AUTH_MW --> FB_AUTH
    SESSION_MGR --> SANDBOX_MGR
    SESSION_MGR --> HISTORY_REPO
    HISTORY_REPO --> FIRESTORE
    WS_EP --> WS_HANDLER
    WS_HANDLER --> ORCH
    RUNTIME_CFG --> CRYPTO_MOD
    SCREEN_TOOL --> SANDBOX_MGR
    COMPUTER_TOOL --> SANDBOX_MGR
    BASH_TOOL --> SANDBOX_MGR
    BROWSER_TOOL --> SANDBOX_MGR
    SANDBOX_MGR --> E2B
    E2B --> VNC_STREAM
    VNC_STREAM -.-> DESKTOP
```

### Session loop

```mermaid
sequenceDiagram
    participant User
    participant FE as Frontend
    participant WS as WebSocket
    participant Orch as Orchestrator
    participant Tools as Tools
    participant E2B as Sandbox

    User->>FE: Type or speak
    FE->>WS: text / audio
    WS->>Orch: turn
    loop Until done
        Orch->>Tools: screenshot / click / type / bash / browse
        Tools->>E2B: act on desktop
        E2B-->>Tools: result
        Orch-->>WS: stream events
    end
    Orch-->>WS: final response
    WS-->>FE: chat + live desktop
```

### Auth

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant FBAuth as Firebase Auth
    participant API as FastAPI
    participant FS as Firestore

    FE->>FBAuth: Google sign-in
    FBAuth-->>FE: ID token
    FE->>API: REST with Bearer token
    API->>FS: upsert user
    API-->>FE: session + WS ticket
    FE->>API: WebSocket with ticket
```

### Deploy

```mermaid
graph LR
    USERS[Users] --> CR_FE[Cloud Run frontend]
    CR_FE --> CR_BE[Cloud Run backend]
    CR_BE --> FS_DB[(Firestore)]
    CR_BE --> FB_A[Firebase Auth]
    CR_BE --> SANDBOX[E2B desktops]
    CR_BE --> MODELS[Your model providers]
```

</details>

## Demo

[4-minute walkthrough](https://www.youtube.com/watch?v=9g9S6vdoNbA) — browse, terminal, and working on a real desktop.
