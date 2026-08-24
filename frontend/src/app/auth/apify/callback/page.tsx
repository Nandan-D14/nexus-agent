/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

export default function ApifyCallbackPage() {
  return (
    <OauthCallbackPage
      name="Apify"
      exchangePath="/api/v1/auth/apify/exchange"
      messageType="apify_connected"
    />
  );
}
