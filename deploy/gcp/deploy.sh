#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
PROJECT_ID="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"

# Use Artifact Registry (gcr.io is deprecated)
AR_HOST="${REGION}-docker.pkg.dev"
AR_REPO="${AR_HOST}/${PROJECT_ID}/nexus"
AGENT_IMAGE="${AR_REPO}/nexus-agent"
FRONTEND_IMAGE="${AR_REPO}/nexus-frontend"

# Resolve paths relative to this script (deploy/gcp/)
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

echo "=== NEXUS Deploy to Cloud Run ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo ""

# ── 0. Create Artifact Registry repo (idempotent) ─────────────
echo "Ensuring Artifact Registry repository exists..."
gcloud artifacts repositories create nexus \
  --project="${PROJECT_ID}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="NEXUS container images" 2>/dev/null || true

# ── 1. Build & Push Agent Image ───────────────────────────────
echo "Building agent image..."
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${AGENT_IMAGE}" \
  "${AGENT_DIR}"

# ── 2. Deploy Agent Service (first — need its URL for frontend) ─
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
  --set-secrets="E2B_API_KEY=e2b-api-key:latest,GOOGLE_API_KEY=google-api-key:latest" \
  --set-env-vars="FIREBASE_PROJECT_ID=${FB_PROJECT_ID}"

AGENT_URL=$(gcloud run services describe nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')

echo "Agent URL: ${AGENT_URL}"
AGENT_WS_URL="${AGENT_URL/https:/wss:}"

# ── 3. Build Frontend Image (NEXT_PUBLIC_* baked in at build time) ─
# gcloud builds submit does not support --build-arg; substitutions via cloudbuild.yaml instead
echo "Building frontend image..."
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config="${FRONTEND_DIR}/cloudbuild.yaml" \
  --substitutions="_IMAGE=${FRONTEND_IMAGE},_NEXT_PUBLIC_FIREBASE_API_KEY=${FB_API_KEY},_NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${FB_AUTH_DOMAIN},_NEXT_PUBLIC_FIREBASE_PROJECT_ID=${FB_PROJECT_ID},_NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=${FB_STORAGE_BUCKET},_NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${FB_MESSAGING_SENDER_ID},_NEXT_PUBLIC_FIREBASE_APP_ID=${FB_APP_ID},_NEXT_PUBLIC_USE_FIREBASE_EMULATORS=false,_NEXT_PUBLIC_AGENT_WS_URL=${AGENT_WS_URL}" \
  "${FRONTEND_DIR}"

# ── 4. Deploy Frontend Service ────────────────────────────────
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

FRONTEND_URL=$(gcloud run services describe nexus-frontend \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')

# ── 5. Update Agent CORS with actual frontend URL ─────────────
echo "Updating agent CORS origin..."
gcloud run services update nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="FRONTEND_URL=${FRONTEND_URL}"

echo ""
echo "=== Deployment Complete ==="
echo "Frontend: ${FRONTEND_URL}"
echo "Agent:    ${AGENT_URL}"
