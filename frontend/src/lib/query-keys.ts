/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

export const queryKeys = {
  quota: () => ["quota"] as const,
  sessions: {
    recent: (limit: number) => ["sessions", "recent", limit] as const,
    active: () => ["sessions", "active"] as const,
  },
  history: (q: string) => ["history", { q }] as const,
  library: (q: string) => ["library", { q }] as const,
  integrations: {
    catalog: () => ["integrations", "catalog"] as const,
    connections: () => ["integrations", "connections"] as const,
  },
  skills: () => ["skills"] as const,
  skill: (skillId: string) => ["skills", skillId] as const,
  skillsCatalog: (source: string) => ["skills", "catalog", source] as const,
  templates: () => ["templates"] as const,
  dashboard: {
    stats: () => ["dashboard", "stats"] as const,
    usage: (days: number) => ["dashboard", "usage", days] as const,
  },
};
