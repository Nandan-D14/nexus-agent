/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

/** Handles the Treg OAuth redirect after the user grants MCP access. */
export default function TregCallbackPage() {
  return (
    <OauthCallbackPage
      name="Treg"
      exchangePath="/api/v1/auth/treg/exchange"
      messageType="treg_connected"
    />
  );
}
