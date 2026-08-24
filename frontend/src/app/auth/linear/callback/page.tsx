/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

export default function LinearCallbackPage() {
  return (
    <OauthCallbackPage
      name="Linear"
      exchangePath="/api/v1/auth/linear/exchange"
      messageType="linear_connected"
    />
  );
}
