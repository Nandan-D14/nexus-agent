/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { cx } from "@/utils/cx";

type Props = {
  label: string;
  className?: string;
};

/** AICSS Thinking State — shimmer label while the agent is reasoning. */
export function ThinkingState({ label, className }: Props) {
  return (
    <span className={cx("text-body-medium agent-progress-loading-text", className)}>
      {label}
    </span>
  );
}
