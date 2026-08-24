/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { SettingsApi } from "@/components/application/settings/settings-api";

function ApiSettingsBody() {
  const searchParams = useSearchParams();
  return <SettingsApi forceSetupBanner={searchParams.get("setup") === "1"} />;
}

export default function ApiSettingsPage() {
  return (
    <Suspense fallback={<div className="text-body-2-regular text-text-secondary">Loading…</div>}>
      <ApiSettingsBody />
    </Suspense>
  );
}
