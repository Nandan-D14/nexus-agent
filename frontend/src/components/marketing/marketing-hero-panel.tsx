/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { ReactNode } from "react";

type MarketingHeroPanelProps = {
  children: ReactNode;
  className?: string;
  /** Extra padding / size; default matches home CTA */
  size?: "default" | "compact";
};

/**
 * Blue rounded panel with white dot grid — same treatment as the home CTA.
 */
export function MarketingHeroPanel({
  children,
  className = "",
  size = "default",
}: MarketingHeroPanelProps) {
  const padding =
    size === "compact" ? "p-10 md:p-14" : "p-12 md:p-20";

  return (
    <div
      className={`relative rounded-[3rem] ${padding} overflow-hidden text-center bg-blue-600 dark:bg-blue-600 shadow-2xl shadow-blue-500/20 ${className}`}
    >
      <div className="absolute inset-0 opacity-10 bg-[radial-gradient(circle_at_2px_2px,#fff_1px,transparent_0)] bg-[size:24px_24px]" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
