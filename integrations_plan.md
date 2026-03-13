# Integrations Plan

This document details the plan to add an "Integrations" section to the Virtual Voice Agent, enabling users to connect third-party services like Google Drive and Model Context Protocol (MCP) servers.

## 1. UI Updates (Frontend)

### Sidebar additions
- Add an "Integrations" (`/integrations`) link to the main navigation sidebar.
- Use a relevant icon (e.g., `Blocks`, `Puzzle`, or `Link` from `lucide-react`).

### Integrations Page (`/integrations`)
- Create a new page displaying a grid/list of available integrations.
- **Google Account / Drive**:
  - Details: "Connect your Google Account to allow the agent to read and create Google Docs."
  - Action: "Connect Google" button that triggers Firebase `signInWithPopup(auth, googleProvider)`.
  - State: Show "Connected" if the user has an active Google session with required scopes.
- **MCP Servers (Local/Remote)**:
  - Details: "Add custom Model Context Protocol servers to connect to local databases, GitHub, etc."
  - Action: "Add Server" button to configure a new MCP connection (URL or local script path).
  - State: List Active/Inactive servers.

## 2. Backend Updates (Agent/Nexus)

### Authentication (`agent/nexus/auth.py`)
- Enhance the token verification to accept Google OAuth tokens (required for Drive API access).
- Securely store these tokens either in the user's Firestore document or the in-memory session.

### MCP Client Manager (`agent/nexus/mcp_client.py`)
- Implement an MCP Client that can connect to multiple servers simultaneously.
- When an integration is enabled from the UI, the backend will dynamically launch or connect to the specified MCP Server, fetch its tools, and dynamically register those tools with the ADK `Runner`.

### Google Drive Tools (`agent/nexus/tools/google_drive.py`)
- Add specific tools `search_drive`, `read_document`, and `create_document` that utilize the Google API Client.
- These tools should fetch the user's stored OAuth token from the session when called by the agent.

## 3. Storage
- **Firestore / Database**: Need a collection `user_integrations` to store connection preferences (which MCP servers are active, Google API refresh tokens if persistent access is needed).

## 4. Execution Steps
1. Create the Integrations page layout and route in Next.js.
2. Add the Sidebar navigation link.
3. Implement the Google Sign-in flow in the newly created Integrations page.
4. Establish the MCP Client wrapper in the Python backend.
5. Create endpoints in `server.py` to list and toggle active MCP integrations.
