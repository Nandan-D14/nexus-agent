/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

/** Handles the Exa OAuth redirect after the user grants MCP access. */
export default function ExaCallbackPage() {
  return (
    <OauthCallbackPage
      name="Exa"
      exchangePath="/api/v1/auth/exa/exchange"
      messageType="exa_connected"
    />
  );
}
