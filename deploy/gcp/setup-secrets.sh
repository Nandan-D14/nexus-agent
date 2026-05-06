#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID}"

echo "Setting up GCP Secret Manager secrets for NEXUS..."

# Create secrets (will fail silently if they already exist)
gcloud secrets create e2b-api-key --project="${PROJECT_ID}" 2>/dev/null || true
gcloud secrets create google-api-key --project="${PROJECT_ID}" 2>/dev/null || true
gcloud secrets create jwt-secret --project="${PROJECT_ID}" 2>/dev/null || true
gcloud secrets create google-oauth-client-secret --project="${PROJECT_ID}" 2>/dev/null || true

echo "Secrets created. Add values with:"
echo "  echo -n 'YOUR_KEY' | gcloud secrets versions add e2b-api-key --data-file=- --project=${PROJECT_ID}"
echo "  echo -n 'YOUR_KEY' | gcloud secrets versions add google-api-key --data-file=- --project=${PROJECT_ID}"
echo "  echo -n 'YOUR_JWT_SECRET' | gcloud secrets versions add jwt-secret --data-file=- --project=${PROJECT_ID}"
echo "  echo -n 'YOUR_OAUTH_SECRET' | gcloud secrets versions add google-oauth-client-secret --data-file=- --project=${PROJECT_ID}"
