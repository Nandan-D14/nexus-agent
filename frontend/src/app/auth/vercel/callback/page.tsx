/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

export default function VercelCallbackPage() {
  return (
    <OauthCallbackPage
      name="Vercel"
      exchangePath="/api/v1/auth/vercel/exchange"
      messageType="vercel_connected"
    />
  );
}
