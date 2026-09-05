/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useCallback, useRef, useEffect } from "react";

export type UseResizableSplitOptions = {
  defaultPercent?: number;
  minLeftPx?: number;
  minRightPx?: number;
  minPercent?: number;
  maxPercent?: number;
  collapseRightThresholdPx?: number;
  onCollapseRight?: () => void;
  storageKey?: string;
};

export function useResizableSplit({
  defaultPercent = 38,
  minLeftPx = 360,
  minRightPx = 420,
  minPercent = 25,
  maxPercent = 65,
  collapseRightThresholdPx = 100,
  onCollapseRight,
  storageKey = "cocomputer_split_ratio",
}: UseResizableSplitOptions = {}) {
  const [percent, setPercent] = useState<number>(() => {
    if (typeof window === "undefined") return defaultPercent;
    try {
      const saved = localStorage.getItem(storageKey);
      const parsed = saved ? parseFloat(saved) : NaN;
      return !isNaN(parsed) && parsed >= minPercent && parsed <= maxPercent
        ? parsed
        : defaultPercent;
    } catch {
      return defaultPercent;
    }
  });

  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const leftPaneRef = useRef<HTMLDivElement>(null);
  const currentPercentRef = useRef(percent);
  const percentRef = useRef(percent);
  percentRef.current = percent;
  const shouldCollapseRef = useRef(false);
  const onCollapseRightRef = useRef(onCollapseRight);
  onCollapseRightRef.current = onCollapseRight;
  const rafIdRef = useRef<number | null>(null);

  // Synchronize leftPane style on initial load and when percent changes outside of drag
  useEffect(() => {
    if (!isDragging && leftPaneRef.current) {
      leftPaneRef.current.style.width = `${percent}%`;
    }
  }, [percent, isDragging]);

  const startDragging = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setIsDragging(true);
    shouldCollapseRef.current = false;
    if (containerRef.current) {
      containerRef.current.setAttribute("data-resizing", "true");
    }
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const resetToDefault = useCallback(() => {
    setPercent(defaultPercent);
    if (leftPaneRef.current) {
      leftPaneRef.current.style.width = `${defaultPercent}%`;
    }
    try {
      localStorage.setItem(storageKey, String(defaultPercent));
    } catch {
      // ignore
    }
  }, [defaultPercent, storageKey]);

  useEffect(() => {
    if (!isDragging) return;

    const onPointerMove = (e: PointerEvent) => {
      const container = containerRef.current;
      const leftPane = leftPaneRef.current;
      if (!container || !leftPane) return;

      const rect = container.getBoundingClientRect();
      const clientX = e.clientX - rect.left;
      const totalWidth = rect.width;

      if (totalWidth <= 0) return;

      // Check if dragged fully to the right (within collapse threshold)
      if (clientX >= totalWidth - collapseRightThresholdPx) {
        shouldCollapseRef.current = true;
        if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = requestAnimationFrame(() => {
          leftPane.style.width = "100%";
        });
        return;
      }

      shouldCollapseRef.current = false;

      // Hard pixel constraints
      const clampedX = Math.max(
        minLeftPx,
        Math.min(totalWidth - minRightPx, clientX),
      );

      // Percentage conversion
      const rawPercent = (clampedX / totalWidth) * 100;
      const clampedPercent = Math.max(
        minPercent,
        Math.min(maxPercent, rawPercent),
      );

      currentPercentRef.current = clampedPercent;

      // Direct DOM manipulation via RAF - 60fps with ZERO React re-renders during drag
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = requestAnimationFrame(() => {
        leftPane.style.width = `${clampedPercent}%`;
      });
    };

    const onPointerUp = () => {
      setIsDragging(false);
      if (containerRef.current) {
        containerRef.current.removeAttribute("data-resizing");
      }
      document.body.style.cursor = "";
      document.body.style.userSelect = "";

      if (shouldCollapseRef.current) {
        shouldCollapseRef.current = false;
        // Restore previous split width on leftPane element so it's ready when desktop re-opens
        if (leftPaneRef.current) {
          leftPaneRef.current.style.width = `${percentRef.current}%`;
        }
        onCollapseRightRef.current?.();
        return;
      }

      const finalPercent = currentPercentRef.current;
      setPercent(finalPercent);

      try {
        localStorage.setItem(storageKey, String(finalPercent));
      } catch {
        // ignore
      }
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, minLeftPx, minRightPx, minPercent, maxPercent, collapseRightThresholdPx, storageKey]);

  return {
    percent,
    isDragging,
    containerRef,
    leftPaneRef,
    startDragging,
    resetToDefault,
  };
}
