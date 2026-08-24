"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/base/buttons/button";
import { fetchUserQuota } from "@/lib/user-settings";
import type { PlanQuota } from "@/lib/message-types";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

function credits(quota: PlanQuota | null) {
  const used = quota?.credits?.used ?? quota?.used ?? 0;
  const limit = quota?.credits?.limit ?? quota?.limit ?? 0;
  const remaining = quota?.credits?.remaining ?? quota?.remaining ?? Math.max(limit - used, 0);
  return { used, limit, remaining };
}

export function SettingsBilling() {
  const [quota, setQuota] = useState<PlanQuota | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchUserQuota()
      .then((next) => {
        if (!cancelled) setQuota(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load billing.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { used, limit, remaining } = credits(quota);
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const name = quota?.plan_name || quota?.plan?.name || "Starter";
  const price = quota?.price_usd ?? quota?.plan?.price_usd ?? 0;

  return (
    <div className="flex w-full flex-col gap-6">
      {error ? (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {error}
        </div>
      ) : null}

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Plan</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow label="Current plan" description={loading ? "Loading…" : price > 0 ? `$${price}/mo` : "Internal entitlement"}>
            <span className="text-body-medium text-text-primary">{loading ? "…" : name}</span>
          </SettingsRow>
          <SettingsRow label="Credits used" description={`${used.toLocaleString()} of ${limit.toLocaleString()}`}>
            <span className="text-body-medium text-text-primary">{percent}%</span>
          </SettingsRow>
          <SettingsRow label="Credits remaining">
            <span className="text-body-medium text-text-primary">{remaining.toLocaleString()}</span>
          </SettingsRow>
        </SettingsCard>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-background-tertiary-default">
        <div
          className="h-full rounded-full bg-blue-500 transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>

      <Button
        variant="secondary"
        size="small"
        className="w-fit"
        onClick={() => {
          window.location.assign("/pricing");
        }}
      >
        Upgrade plan
      </Button>
    </div>
  );
}
