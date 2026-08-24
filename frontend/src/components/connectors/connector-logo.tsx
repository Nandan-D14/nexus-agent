/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Cloud } from "lucide-react";

import {
  invertLogoInDark,
  logoFillsTile,
  logoTileClass,
  providerLogo,
  providerLogoDark,
} from "@/lib/connectors";
import { cx } from "@/utils/cx";

export function ConnectorLogo({
  provider,
  name,
  size = "md",
}: {
  provider: string;
  name: string;
  size?: "sm" | "md";
}) {
  const src = providerLogo(provider);
  const darkSrc = providerLogoDark(provider);
  const fillsTile = logoFillsTile(provider);
  const box = size === "sm" ? "size-10" : "size-11";
  const icon = size === "sm" ? "size-5" : "size-6";
  const image = size === "sm" ? "size-7" : "size-8";
  const imgClass = cx("object-contain", fillsTile ? "size-full" : image);

  return (
    <span
      className={cx(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-xl",
        logoTileClass(provider),
        box,
      )}
    >
      {src ? (
        darkSrc ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element -- local and remote brand marks */}
            <img src={src} alt="" className={cx(imgClass, "dark:hidden")} />
            {/* eslint-disable-next-line @next/next/no-img-element -- local and remote brand marks */}
            <img src={darkSrc} alt="" className={cx(imgClass, "hidden dark:block")} />
          </>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- local and remote brand marks
          <img
            src={src}
            alt=""
            className={cx(imgClass, invertLogoInDark(provider) && "dark:invert")}
          />
        )
      ) : (
        <Cloud className={cx(icon, "text-zinc-500")} />
      )}
      <span className="sr-only">{name}</span>
    </span>
  );
}
