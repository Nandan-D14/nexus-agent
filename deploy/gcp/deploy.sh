#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"          # Cloud Run / Artifact Registry region
GEMINI_REGION="${GOOGLE_GEMINI_REGION:-global}"        # Gemini API region (Gemini 3 requires "global")

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
GOOGLE_OAUTH_CLIENT_SECRET="${GOOGLE_OAUTH_CLIENT_SECRET:-}"
REQUIRE_BYOK="${REQUIRE_BYOK:-false}"
BETA_ENFORCE_BYOK="${BETA_ENFORCE_BYOK:-true}"
BYOK_ENCRYPTION_KEY_SECRET="${BYOK_ENCRYPTION_KEY_SECRET:-}"
SHARED_ACCESS_CODE="${SHARED_ACCESS_CODE:-}"
BETA_ADMIN_EMAILS="${BETA_ADMIN_EMAILS:?Set BETA_ADMIN_EMAILS}"
BETA_GOOGLE_SHEET_ID="${BETA_GOOGLE_SHEET_ID:?Set BETA_GOOGLE_SHEET_ID}"
BETA_GOOGLE_SHEET_NAME="${BETA_GOOGLE_SHEET_NAME:-beta_applications}"
JWT_SECRET="${JWT_SECRET:?Set JWT_SECRET}"

AGENT_SECRET_FLAGS=(
  "--set-secrets=E2B_API_KEY=e2b-api-key:latest"
)

if [[ -n "${BYOK_ENCRYPTION_KEY_SECRET}" ]]; then
  AGENT_SECRET_FLAGS+=(
    "--set-secrets=BYOK_ENCRYPTION_KEY=${BYOK_ENCRYPTION_KEY_SECRET}:latest"
  )
fi

AGENT_ENV_VARS=(
  "APP_ENV=production"
  "FIREBASE_PROJECT_ID=${FB_PROJECT_ID}"
  "GOOGLE_PROJECT_ID=${PROJECT_ID}"
  "GOOGLE_CLOUD_REGION=${GEMINI_REGION}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "GOOGLE_CLOUD_LOCATION=${GEMINI_REGION}"
  "GOOGLE_GENAI_USE_VERTEXAI=true"
  "GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}"
  "GOOGLE_OAUTH_CLIENT_SECRET=${GOOGLE_OAUTH_CLIENT_SECRET}"
  "REQUIRE_BYOK=${REQUIRE_BYOK}"
  "BETA_ENFORCE_BYOK=${BETA_ENFORCE_BYOK}"
  "SHARED_ACCESS_CODE=${SHARED_ACCESS_CODE}"
  "BETA_ADMIN_EMAILS=${BETA_ADMIN_EMAILS}"
  "BETA_GOOGLE_SHEET_ID=${BETA_GOOGLE_SHEET_ID}"
  "BETA_GOOGLE_SHEET_NAME=${BETA_GOOGLE_SHEET_NAME}"
  "JWT_SECRET=${JWT_SECRET}"
)
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
  --allow-unauthenticated \
  "${AGENT_SECRET_FLAGS[@]}" \
  --set-env-vars="${AGENT_ENV_VARS_CSV}"

AGENT_URL="$(gcloud run services describe nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo "Agent URL: ${AGENT_URL}"
AGENT_WS_URL="${AGENT_URL/https:/wss:}"

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
