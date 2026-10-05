#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_PROJECT_ID:?Set GOOGLE_PROJECT_ID}"

# Secrets read by Cloud Run via --set-secrets (CI and deploy.sh).
SECRETS=(
  e2b-api-key
  google-api-key
  jwt-secret
  byok-encryption-key
  google-oauth-client-secret
  slack-client-secret
  task-worker-auth-token
  qwen-api-key
)

echo "Setting up GCP Secret Manager secrets for NEXUS..."

# Create secrets (will fail silently if they already exist)
for secret in "${SECRETS[@]}"; do
  gcloud secrets create "${secret}" --project="${PROJECT_ID}" 2>/dev/null || true
done

echo "Secrets created. Add values with:"
for secret in "${SECRETS[@]}"; do
  echo "  echo -n 'VALUE' | gcloud secrets versions add ${secret} --data-file=- --project=${PROJECT_ID}"
done
echo
echo "IMPORTANT: byok-encryption-key must equal the key production already uses,"
echo "otherwise stored user API keys can no longer be decrypted."
echo "Grant the Cloud Run runtime service account roles/secretmanager.secretAccessor."
