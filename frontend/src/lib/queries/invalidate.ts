/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { QueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";

export function invalidateSessionLists(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: ["sessions"] });
  void queryClient.invalidateQueries({ queryKey: ["history"] });
}

export function invalidateIntegrations(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.integrations.catalog() });
  void queryClient.invalidateQueries({ queryKey: queryKeys.integrations.connections() });
  void queryClient.invalidateQueries({ queryKey: queryKeys.calendar.eventsRoot() });
}
