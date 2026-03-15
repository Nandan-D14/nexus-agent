#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
PROJECT_ID="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
AGENT_IMAGE="gcr.io/${PROJECT_ID}/nexus-agent"
FRONTEND_IMAGE="gcr.io/${PROJECT_ID}/nexus-frontend"

# Firebase Web SDK values (public — safe to embed in frontend JS)
FB_API_KEY="${FIREBASE_API_KEY:?Set FIREBASE_API_KEY}"
FB_AUTH_DOMAIN="virtual-voice-agent-55414.firebaseapp.com"
FB_PROJECT_ID="virtual-voice-agent-55414"
FB_STORAGE_BUCKET="virtual-voice-agent-55414.firebasestorage.app"
FB_MESSAGING_SENDER_ID="962895097177"
FB_APP_ID="1:962895097177:web:6804ee8cc23073a9c03048"

echo "=== NEXUS Deploy to Cloud Run ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo ""

# ── 1. Build & Push Agent Image ───────────────────────────────
echo "Building agent image..."
gcloud builds submit --project="${PROJECT_ID}" --tag="${AGENT_IMAGE}" ../agent/

# ── 2. Deploy Agent Service (must go first so we get its URL) ─
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

# ── 3. Build Frontend Image (with NEXT_PUBLIC_* build args) ───
echo "Building frontend image..."
gcloud builds submit --project="${PROJECT_ID}" --tag="${FRONTEND_IMAGE}" \
  --build-arg="NEXT_PUBLIC_FIREBASE_API_KEY=${FB_API_KEY}" \
  --build-arg="NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${FB_AUTH_DOMAIN}" \
  --build-arg="NEXT_PUBLIC_FIREBASE_PROJECT_ID=${FB_PROJECT_ID}" \
  --build-arg="NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=${FB_STORAGE_BUCKET}" \
  --build-arg="NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${FB_MESSAGING_SENDER_ID}" \
  --build-arg="NEXT_PUBLIC_FIREBASE_APP_ID=${FB_APP_ID}" \
  --build-arg="NEXT_PUBLIC_USE_FIREBASE_EMULATORS=false" \
  --build-arg="NEXT_PUBLIC_AGENT_WS_URL=${AGENT_WS_URL}" \
  ../frontend/

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

# ── 5. Update Agent with correct FRONTEND_URL for CORS ───────
echo "Updating agent CORS origin..."
gcloud run services update nexus-agent \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="FRONTEND_URL=${FRONTEND_URL}"

echo ""
echo "=== Deployment Complete ==="
echo "Frontend: ${FRONTEND_URL}"
echo "Agent:    ${AGENT_URL}"
