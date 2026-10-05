/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect } from "react";
import Link from "next/link";

/** Route-level error boundary: a render error shows this instead of a blank page. */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[route-error]", error);
  }, [error]);

  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-lg font-semibold text-text-primary">Something went wrong</h1>
      <p className="max-w-md text-sm text-text-tertiary">
        This page hit an unexpected error. Your sessions and files are safe.
        {error.digest ? ` (ref ${error.digest})` : null}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={reset}
          className="rounded-lg border border-input-border px-3 py-1.5 text-sm text-text-primary hover:bg-dropdown-item-hover-background"
        >
          Try again
        </button>
        <Link
          href="/"
          className="rounded-lg px-3 py-1.5 text-sm text-text-tertiary hover:text-text-primary"
        >
          Go home
        </Link>
      </div>
    </main>
  );
}
