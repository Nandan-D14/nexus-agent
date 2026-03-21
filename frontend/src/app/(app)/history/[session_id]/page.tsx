"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function HistorySessionRedirectPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = String(params.session_id || "");

  useEffect(() => {
    if (!sessionId) {
      router.replace("/history");
      return;
    }
    router.replace(`/session/${sessionId}`);
  }, [router, sessionId]);

  return (
    <div className="flex h-full min-h-[40vh] items-center justify-center p-8">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="h-8 w-8 rounded-full border-4 border-cyan-600 border-t-transparent animate-spin" />
        <p className="text-sm text-zinc-500">Opening thread…</p>
      </div>
    </div>
  );
}
