/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

const SCHEDULING_RE =
  /\b(calendar|meeting|meetings|appointment|appointments|invite|attendee|attendees|schedule|scheduled|scheduling|reschedule|event|events|remind(?:er|ers)?|todo|to-?do|due\b|deadline|google task|google tasks)\b/i;

export type SchedulingConnector = {
  connection_id: string;
  provider: string;
};

export function looksLikeSchedulingPrompt(text: string): boolean {
  return SCHEDULING_RE.test(text.trim());
}

export function isGoogleSchedulingConnector(connector: SchedulingConnector): boolean {
  return connector.provider === "google_calendar" || connector.provider === "google_tasks";
}

export function googleSuiteConnected(connectors: SchedulingConnector[]): boolean {
  return connectors.some(isGoogleSchedulingConnector);
}

export function schedulingConnectorIds(connectors: SchedulingConnector[]): string[] {
  return connectors.filter(isGoogleSchedulingConnector).map((connector) => connector.connection_id);
}

/** When the tool picker is already restricted, add Calendar/Tasks so creates are not blocked. */
export function withSchedulingConnectors(
  text: string,
  selectedConnectorIds: string[],
  selectedToolIds: string[],
  available: SchedulingConnector[],
): string[] {
  const pickerRestricted = selectedConnectorIds.length > 0 || selectedToolIds.length > 0;
  if (!pickerRestricted || !looksLikeSchedulingPrompt(text)) {
    return selectedConnectorIds;
  }
  const extra = schedulingConnectorIds(available);
  if (extra.length === 0) {
    return selectedConnectorIds;
  }
  return Array.from(new Set([...selectedConnectorIds, ...extra]));
}
