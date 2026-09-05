/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

export default function CloudflareCallbackPage() {
  return (
    <OauthCallbackPage
      name="Cloudflare"
      exchangePath="/api/v1/auth/cloudflare/exchange"
      messageType="cloudflare_connected"
    />
  );
}
