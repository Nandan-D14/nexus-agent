/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { OauthCallbackPage } from "@/components/auth/oauth-callback-page";

export const dynamic = "force-dynamic";

export default function SlackCallbackPage() {
  return (
    <OauthCallbackPage
      name="Slack"
      exchangePath="/api/v1/auth/slack/exchange"
      messageType="slack_connected"
    />
  );
}
