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

export function BeamsBackground() {
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

  return (
    <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
      <div className="absolute inset-0 [mask-image:linear-gradient(to_bottom,black_60%,transparent_100%)]">
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
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-background to-transparent" />
    </div>
  );
}
