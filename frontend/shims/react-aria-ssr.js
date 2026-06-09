"use client";

// Shim for @react-aria/ssr — bypasses the broken re-export chain
// (react-aria/SSRProvider → react-aria/private/ssr/SSRProvider) that fails
// under webpack's static analysis in Next.js 16.
import { useSyncExternalStore, useContext, useState, createContext, Fragment, createElement, useId } from "react";

const defaultContext = { prefix: String(Math.round(Math.random() * 10000000000)), current: 0 };
const SSRContext = createContext(defaultContext);
const IsSSRContext = createContext(false);

function subscribe() { return () => {}; }
function getSnapshot() { return false; }
function getServerSnapshot() { return true; }

export function useIsSSR() {
  if (typeof useSyncExternalStore === "function") {
    return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  }
  return useContext(IsSSRContext);
}

export function SSRProvider(props) {
  return createElement(Fragment, null, props.children);
}

export function useSSRSafeId(defaultId) {
  const id = useId();
  return defaultId || `react-aria-${id}`;
}
