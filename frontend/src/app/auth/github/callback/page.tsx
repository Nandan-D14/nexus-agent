/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

export default function GitHubCallbackPage() {
  return (
    <OauthCallbackPage
      name="GitHub"
      exchangePath="/api/v1/auth/github/exchange"
      messageType="github_connected"
    />
  );
}
