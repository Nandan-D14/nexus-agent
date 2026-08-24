"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";

const Beams = dynamic(() => import("./Beams"), { ssr: false });

function LightBlurFallback() {
  return (
    <div className="absolute inset-0 z-0 pointer-events-none flex items-center justify-center">
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-blue-500/10 dark:bg-blue-500/20 blur-[120px] rounded-full" />
    </div>
  );
}

type BeamsBackgroundProps = {
  /** Hero fades out toward the next section; footer keeps beams across the block. */
  variant?: "hero" | "footer";
};

export function BeamsBackground({ variant = "hero" }: BeamsBackgroundProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    setMounted(true);
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduceMotion(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const showBeams = mounted && resolvedTheme === "dark" && !reduceMotion;

  if (!showBeams) {
    return <LightBlurFallback />;
  }

  const maskClass =
    variant === "footer"
      ? "[mask-image:linear-gradient(to_bottom,transparent_0%,black_20%,black_100%)]"
      : "[mask-image:linear-gradient(to_bottom,black_60%,transparent_100%)]";

  return (
    <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
      <div className={`absolute inset-0 ${maskClass}`}>
        <Beams
          beamWidth={2}
          beamHeight={15}
          beamNumber={12}
          lightColor="#60a5fa"
          speed={1.5}
          noiseIntensity={1.75}
          scale={0.14}
          rotation={31}
        />
      </div>
      {variant === "hero" ? (
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-background to-transparent" />
      ) : (
        <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-background to-transparent" />
      )}
    </div>
  );
}
