/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo } from "react";

/** Render an HTML string in a sandboxed frame (no same-origin access). */
export function HtmlFrame({
  html,
  title,
  className = "h-full w-full bg-white",
}: {
  html: string;
  title: string;
  className?: string;
}) {
  const url = useMemo(() => {
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    return URL.createObjectURL(blob);
  }, [html]);

  useEffect(() => {
    return () => URL.revokeObjectURL(url);
  }, [url]);

  return (
    <iframe
      src={url}
      title={title}
      className={className}
      sandbox="allow-scripts allow-forms allow-modals"
    />
  );
}
