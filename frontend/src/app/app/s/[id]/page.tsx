/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";

import { AppShellSkeleton } from "@/components/app-shell-skeleton";

const SessionWorkspace = dynamic(
  () =>
    import("@/components/session/session-workspace").then(
      (mod) => mod.SessionWorkspace,
    ),
  { ssr: false, loading: () => <AppShellSkeleton /> },
);

export default function SessionPage() {
  const params = useParams();
  return <SessionWorkspace sessionId={String(params.id || "")} />;
}
