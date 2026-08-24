"use client";

import { cx } from "@/utils/cx";

export function LlmProviderLogo({
  src,
  name,
  invertInDark = false,
  className,
}: {
  src?: string;
  name: string;
  invertInDark?: boolean;
  className?: string;
}) {
  if (!src) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- local brand marks
    <img
      src={src}
      alt=""
      className={cx(
        "size-4 shrink-0 object-contain",
        invertInDark && "dark:invert",
        className,
      )}
    />
  );
}
