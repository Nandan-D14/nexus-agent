/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

/** Handles the Google OAuth redirect after the user grants Drive access. */
export default function GoogleDriveCallbackPage() {
  return (
    <OauthCallbackPage
      name="Google Drive"
      exchangePath="/api/v1/auth/google-drive/exchange"
      messageType="google_drive_connected"
    />
  );
}
