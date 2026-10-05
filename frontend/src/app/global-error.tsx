/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect } from "react";

/**
 * Last-resort boundary for errors thrown by the root layout itself (providers,
 * auth bootstrap). It replaces the whole document, so it cannot rely on the
 * app's CSS and uses inline styles.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global-error]", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          fontFamily: "system-ui, sans-serif",
          background: "#0a0a0c",
          color: "#e4e4e7",
          textAlign: "center",
          padding: 24,
        }}
      >
        <h1 style={{ fontSize: 18, margin: 0 }}>CoComputer failed to load</h1>
        <p style={{ fontSize: 14, color: "#a1a1aa", maxWidth: 420, margin: 0 }}>
          An unexpected error stopped the app from starting.
          {error.digest ? ` (ref ${error.digest})` : null}
        </p>
        <button
          type="button"
          onClick={reset}
          style={{
            border: "1px solid #3f3f46",
            background: "transparent",
            color: "inherit",
            borderRadius: 8,
            padding: "6px 12px",
            cursor: "pointer",
          }}
        >
          Reload
        </button>
      </body>
    </html>
  );
}
