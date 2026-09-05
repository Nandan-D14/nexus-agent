# Artifact Durability Runbook (xlsx/pdf/docx/pptx/html/csv/images)

All sessions, all file types: the exact original bytes are immutable in GCS and
servable forever via `artifact_id`, independent of live sandbox state.

## Layout

- Bucket: `nexus-artifacts-{development,production}` (`storage.py:get_artifact_bucket_name`)
- New blobs: `{session_id}/{run_id}/{artifact_id}/{relative_path}`
- Legacy blobs: `{session_id}/{run_id}/{relative_path}` (read fallback only)
- Preview siblings (docx->pdf, pptx->html): `{session}/{run}/{artifact_id}/{preview_path}`
  stored as `preview_gcs_blob` in artifact metadata.
- Firestore doc: `sessions/{sid}/runs/{rid}/artifacts/{aid}` mirrored to
  `users/{owner}/tasks/{task}/artifacts/{aid}` and `.../runs/{rid}/artifacts/{aid}`.
  Metadata must contain `gcs_bucket/gcs_blob/relative_path/content_type`.

## Deploy

1. `firebase deploy --only firestore:indexes` - needs
   `artifacts(ownerId+artifactId)`, `artifacts(sessionId+createdAt)`,
   `artifacts(ownerId+createdAt)` (already in `firestore.indexes.json`).
2. Ensure bucket exists + SA has `storage.objectAdmin` and
   `iam.serviceAccountTokenCreator` (for V4 signed URLs, 1h expiry).
3. Never set bucket TTL/lifecycle delete. Session pause/cleanup must never
   delete blobs - only explicit user-data deletion calls
   `delete_user_artifacts_async`.

## Diagnose 1hr-later sheet failure

- `Could not load this spreadsheet` + console `ARTIFACT_DOC_NOT_FOUND (404)`:
  Firestore doc missing or index not deployed. Check
  `sessions/{sid}/runs/{rid}/artifacts/{aid}` + task mirrors, logs
  `ARTIFACT_DOC_NOT_FOUND / ARTIFACT_INDEX_MISSING`.
- `ARTIFACT_BLOB_MISSING (410)`: doc exists but no GCS bytes (pre-fix upload
  failed or bucket wiped). Regenerate; new uploads are enforced durable.
- `SANDBOX_EPHEMERAL / LIVE_SESSION_NOT_FOUND`: caller used live
  `/sessions/.../files/download` for history. Use
  `/artifacts/{id}/content?session_id=&run_id=` instead. Frontend defaults
  `allowSandbox=false` - only live file browser opts in.
- Signed URL expired after 1h is normal - `/content` proxy + `/download`
  refresh on demand; browser never fetches GCS directly (CORS).

## Backfill pre-fix sheets

If doc has no `gcs_blob`: if sandbox file still alive, re-upload via
`save_as_artifact(path)` (now immutable); else ask agent to regenerate.
Do not copy legacy blob over immutable path - keep both, reader tries
stored > immutable > legacy.
