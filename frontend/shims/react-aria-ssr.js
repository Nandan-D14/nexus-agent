"use client";

// Shim for @react-aria/ssr — bypasses the broken re-export chain
// (react-aria/SSRProvider → react-aria/private/ssr/SSRProvider) that fails
// under webpack's static analysis in Next.js 16.
import { useSyncExternalStore, Fragment, createElement, useId } from "react";

function subscribe() { return () => {}; }
function getSnapshot() { return false; }
function getServerSnapshot() { return true; }

export function useIsSSR() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function SSRProvider(props) {
  return createElement(Fragment, null, props.children);
}

export function useSSRSafeId(defaultId) {
  const id = useId();
  return defaultId || `react-aria-${id}`;
}
