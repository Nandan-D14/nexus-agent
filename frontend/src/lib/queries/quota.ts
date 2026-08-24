/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/lib/auth-context";
import { queryKeys } from "@/lib/query-keys";
import { fetchUserQuota } from "@/lib/user-settings";

export function useQuotaQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.quota(),
    queryFn: fetchUserQuota,
    enabled: Boolean(user),
  });
}
