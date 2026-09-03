/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/** Product shell (logged-in app). Marketing stays at `/`. */

export const APP_HOME = "/app";
export const APP_WORKSPACE = "/app/workspace";
export const APP_DASHBOARD = "/app/dashboard";
export const APP_HISTORY = "/app/history";
export const APP_SCHEDULE = "/app/schedule";
export const APP_LIBRARY = "/app/library";
export const APP_TEMPLATES = "/app/templates";
export const APP_SKILLS = "/app/skills";
export const APP_CONNECTORS = "/app/connectors";
export const APP_SETTINGS = "/app/settings";

export function skillPath(skillId: string): string {
  return `${APP_SKILLS}/${encodeURIComponent(skillId)}`;
}

export function sessionPath(
  sessionId: string,
  query?: string | Record<string, string>,
): string {
  if (!sessionId || sessionId === "new") return APP_HOME;
  const base = `${APP_HOME}/s/${encodeURIComponent(sessionId)}`;
  if (!query) return base;
  const qs = typeof query === "string" ? query.replace(/^\?/, "") : new URLSearchParams(query).toString();
  return qs ? `${base}?${qs}` : base;
}

export function historySessionPath(sessionId: string): string {
  return `${APP_HISTORY}/${encodeURIComponent(sessionId)}`;
}

export function settingsPath(page?: string): string {
  if (!page) return APP_SETTINGS;
  return `${APP_SETTINGS}/${page.replace(/^\/+/, "")}`;
}

export function isSessionWorkspacePath(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return pathname === APP_HOME || pathname.startsWith(`${APP_HOME}/s/`);
}
