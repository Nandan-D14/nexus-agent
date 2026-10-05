#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"          # Cloud Run / Artifact Registry region
GEMINI_REGION="${GOOGLE_GEMINI_REGION:-global}"        # Gemini API region (Gemini 3 requires "global")
TASKS_LOCATION="${GCP_TASKS_LOCATION:-${REGION}}"
TASKS_QUEUE="${GCP_TASKS_QUEUE:-cocomputer-tasks}"

AR_HOST="${REGION}-docker.pkg.dev"
AR_REPO="${AR_HOST}/${PROJECT_ID}/nexus"
AGENT_IMAGE="${AR_REPO}/nexus-agent"
FRONTEND_IMAGE="${AR_REPO}/nexus-frontend"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AGENT_DIR="${ROOT_DIR}/agent"
FRONTEND_DIR="${ROOT_DIR}/frontend"

# Firebase Web SDK values (public — safe to embed in frontend JS)
FB_API_KEY="${FIREBASE_API_KEY:?Set FIREBASE_API_KEY}"
FB_AUTH_DOMAIN="${FIREBASE_AUTH_DOMAIN:?Set FIREBASE_AUTH_DOMAIN}"
FB_PROJECT_ID="${FIREBASE_PROJECT_ID:?Set FIREBASE_PROJECT_ID}"
FB_STORAGE_BUCKET="${FIREBASE_STORAGE_BUCKET:?Set FIREBASE_STORAGE_BUCKET}"
FB_MESSAGING_SENDER_ID="${FIREBASE_MESSAGING_SENDER_ID:?Set FIREBASE_MESSAGING_SENDER_ID}"
FB_APP_ID="${FIREBASE_APP_ID:?Set FIREBASE_APP_ID}"

GOOGLE_OAUTH_CLIENT_ID="${GOOGLE_OAUTH_CLIENT_ID:-}"
REQUIRE_BYOK="${REQUIRE_BYOK:-false}"
BETA_ENFORCE_BYOK="${BETA_ENFORCE_BYOK:-true}"
SHARED_ACCESS_CODE="${SHARED_ACCESS_CODE:-}"
BETA_ADMIN_EMAILS="${BETA_ADMIN_EMAILS:?Set BETA_ADMIN_EMAILS}"
BETA_GOOGLE_SHEET_ID="${BETA_GOOGLE_SHEET_ID:?Set BETA_GOOGLE_SHEET_ID}"
BETA_GOOGLE_SHEET_NAME="${BETA_GOOGLE_SHEET_NAME:-beta_applications}"
# Service account Cloud Tasks uses to mint OIDC tokens for the worker. When set,
# the worker is deployed private (IAM-invoker only) instead of public+token.
TASKS_OIDC_SA="${GCP_TASKS_OIDC_SERVICE_ACCOUNT:-}"

# All secrets come from Secret Manager (see setup-secrets.sh); never env vars.
# Keep this list in sync with .github/workflows/google-cloudrun-docker.yml.
AGENT_SECRET_FLAGS=(
  "--set-secrets=E2B_API_KEY=e2b-api-key:latest"
  "--set-secrets=QWEN_API_KEY=qwen-api-key:latest"
  "--set-secrets=JWT_SECRET=jwt-secret:latest"
  "--set-secrets=BYOK_ENCRYPTION_KEY=byok-encryption-key:latest"
  "--set-secrets=GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest"
  "--set-secrets=SLACK_CLIENT_SECRET=slack-client-secret:latest"
  "--set-secrets=TASK_WORKER_AUTH_TOKEN=task-worker-auth-token:latest"
)

AGENT_ENV_VARS=(
  "APP_ENV=production"
  "MODEL_PROVIDER=qwen"
  "FIREBASE_PROJECT_ID=${FB_PROJECT_ID}"
  "GOOGLE_PROJECT_ID=${PROJECT_ID}"
  "GOOGLE_CLOUD_REGION=${GEMINI_REGION}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "GOOGLE_CLOUD_LOCATION=${GEMINI_REGION}"
  "GOOGLE_GENAI_USE_VERTEXAI=true"
  "GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}"
  "REQUIRE_BYOK=${REQUIRE_BYOK}"
  "BETA_ENFORCE_BYOK=${BETA_ENFORCE_BYOK}"
  "SHARED_ACCESS_CODE=${SHARED_ACCESS_CODE}"
  "BETA_ADMIN_EMAILS=${BETA_ADMIN_EMAILS}"
  "BETA_GOOGLE_SHEET_ID=${BETA_GOOGLE_SHEET_ID}"
  "BETA_GOOGLE_SHEET_NAME=${BETA_GOOGLE_SHEET_NAME}"
  "TASK_WORKER_ENABLED=true"
  "TASK_QUEUE_LOCAL_FALLBACK=false"
  "DURABLE_SUBAGENTS_ENABLED=true"
  "SUBAGENT_LEASE_SECONDS=600"
  "SUBAGENT_HEARTBEAT_INTERVAL_SECONDS=120"
  "SUBAGENT_MAX_MAILBOX_MESSAGES=32"
  "SUBAGENT_PARENT_WAIT_SECONDS=300"
  "GCP_TASKS_PROJECT_ID=${PROJECT_ID}"
  "GCP_TASKS_LOCATION=${TASKS_LOCATION}"
  "GCP_TASKS_QUEUE=${TASKS_QUEUE}"
)
if [[ -n "${TASKS_OIDC_SA}" ]]; then
  AGENT_ENV_VARS+=("GCP_TASKS_OIDC_SERVICE_ACCOUNT=${TASKS_OIDC_SA}")
fi
AGENT_ENV_VARS_CSV="$(IFS=,; printf '%s' "${AGENT_ENV_VARS[*]}")"

echo "=== Co-Computer Deploy to Cloud Run ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo ""

echo "Ensuring Artifact Registry repository exists..."
gcloud artifacts repositories create nexus \
  --project="${PROJECT_ID}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Co-Computer container images" 2>/dev/null || true

echo "Building agent image..."
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${AGENT_IMAGE}" \
  "${AGENT_DIR}"

echo "Ensuring Cloud Tasks queue exists..."
gcloud tasks queues create "${TASKS_QUEUE}" \
  --project="${PROJECT_ID}" \
  --location="${TASKS_LOCATION}" 2>/dev/null || true

echo "Deploying agent service..."
gcloud run deploy nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${AGENT_IMAGE}" \
  --port=8000 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=3600 \
  --concurrency=10 \
  --no-cpu-throttling \
  --allow-unauthenticated \
  --session-affinity \
  "${AGENT_SECRET_FLAGS[@]}" \
  --set-env-vars="${AGENT_ENV_VARS_CSV}"

AGENT_URL="$(gcloud run services describe nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo "Agent URL: ${AGENT_URL}"
echo "Rollback (deployment/version level only; no second runtime mesh):"
echo "  gcloud run services update-traffic nexus-agent --region=${REGION} --to-revisions=PREVIOUS_REVISION=100"
echo "List revisions with:"
echo "  gcloud run revisions list --service=nexus-agent --region=${REGION}"
AGENT_WS_URL="${AGENT_URL/https:/wss:}"

echo "Deploying worker service..."
if [[ -n "${TASKS_OIDC_SA}" ]]; then
  # Only Cloud Tasks (via its OIDC service account) may invoke the worker.
  WORKER_AUTH_FLAG="--no-allow-unauthenticated"
else
  echo "WARNING: GCP_TASKS_OIDC_SERVICE_ACCOUNT not set; worker stays public and relies on X-Worker-Token."
  WORKER_AUTH_FLAG="--allow-unauthenticated"
fi
gcloud run deploy cocomputer-worker \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${AGENT_IMAGE}" \
  --port=8000 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=3600 \
  --concurrency=1 \
  --no-cpu-throttling \
  "${WORKER_AUTH_FLAG}" \
  "${AGENT_SECRET_FLAGS[@]}" \
  --set-env-vars="${AGENT_ENV_VARS_CSV}"
if [[ -n "${TASKS_OIDC_SA}" ]]; then
  gcloud run services add-iam-policy-binding cocomputer-worker \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --member="serviceAccount:${TASKS_OIDC_SA}" \
    --role="roles/run.invoker" >/dev/null
fi

WORKER_URL="$(gcloud run services describe cocomputer-worker \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"
WORKER_TASK_URL="${WORKER_URL}/internal/tasks/run"

echo "Updating agent and worker queue target..."
gcloud run services update nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="GCP_TASKS_WORKER_URL=${WORKER_TASK_URL}"
gcloud run services update cocomputer-worker \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="GCP_TASKS_WORKER_URL=${WORKER_TASK_URL}"

echo "Building frontend image..."
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config="${FRONTEND_DIR}/cloudbuild.yaml" \
  --substitutions="_IMAGE=${FRONTEND_IMAGE},_NEXT_PUBLIC_FIREBASE_API_KEY=${FB_API_KEY},_NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${FB_AUTH_DOMAIN},_NEXT_PUBLIC_FIREBASE_PROJECT_ID=${FB_PROJECT_ID},_NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=${FB_STORAGE_BUCKET},_NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${FB_MESSAGING_SENDER_ID},_NEXT_PUBLIC_FIREBASE_APP_ID=${FB_APP_ID},_NEXT_PUBLIC_USE_FIREBASE_EMULATORS=false,_NEXT_PUBLIC_AGENT_WS_URL=${AGENT_WS_URL}" \
  "${FRONTEND_DIR}"

echo "Deploying frontend service..."
gcloud run deploy nexus-frontend \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${FRONTEND_IMAGE}" \
  --port=3000 \
  --memory=512Mi \
  --cpu=1 \
  --timeout=300 \
  --concurrency=80 \
  --allow-unauthenticated \
  --set-env-vars="AGENT_URL=${AGENT_URL}"

FRONTEND_URL="$(gcloud run services describe nexus-frontend \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo "Updating agent CORS origin..."
gcloud run services update nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="FRONTEND_URL=${FRONTEND_URL}"

echo ""
echo "=== Deployment Complete ==="
echo "Frontend: ${FRONTEND_URL}"
echo "Agent:    ${AGENT_URL}"
echo "Worker:   ${WORKER_URL}"
echo "Queue:    ${TASKS_QUEUE} (${TASKS_LOCATION})"
