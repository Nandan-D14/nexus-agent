"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { Switch } from "@/components/base/switch/switch";
import {
  type ArtifactOpenMode,
  type AutonomyMode,
  type NotificationPrefs,
  fetchUserQuota,
  fetchUserSettings,
  patchAppSettings,
  readAppSettings,
} from "@/lib/user-settings";
import type { PlanQuota } from "@/lib/message-types";
import { PlanArtFlame } from "./plan-art-flame";
import {
  SettingsCard,
  SettingsRow,
  SettingsSectionLabel,
} from "./settings-rows";

const SELECT_TRIGGER = "h-8 w-auto gap-1 rounded-lg px-2 py-1.5";

function planHeadline(quota: PlanQuota | null): string {
  if (!quota) return "Loading…";
  const name = quota.plan_name || quota.plan?.name || "Starter";
  const price = quota.price_usd ?? quota.plan?.price_usd ?? 0;
  return price > 0 ? `${name} $${price}/mo` : name;
}

function creditsUsed(quota: PlanQuota | null): { used: number; limit: number } {
  const used = quota?.credits?.used ?? quota?.used ?? 0;
  const limit = quota?.credits?.limit ?? quota?.limit ?? 0;
  return { used, limit };
}

export function SettingsGeneral({
  planArtSrc,
  onManageLimits,
  onSaved,
}: {
  planArtSrc?: string;
  onManageLimits?: () => void;
  onSaved?: () => void;
}) {
  const [quota, setQuota] = useState<PlanQuota | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autonomyMode, setAutonomyMode] = useState<AutonomyMode>("manual");
  const [artifactOpenMode, setArtifactOpenMode] = useState<ArtifactOpenMode>("in_app");
  const [toggles, setToggles] = useState<NotificationPrefs>({
    critical: true,
    system: false,
    sound: false,
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchUserQuota(), fetchUserSettings()])
      .then(([nextQuota, settings]) => {
        if (cancelled) return;
        const parsed = readAppSettings(settings);
        setQuota(nextQuota);
        setAutonomyMode(parsed.autonomyMode);
        setArtifactOpenMode(parsed.artifactOpenMode);
        setToggles(parsed.notifications);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load settings.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const persist = async (partial: Parameters<typeof patchAppSettings>[0]) => {
    setError(null);
    try {
      await patchAppSettings(partial);
      onSaved?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    }
  };

  const { used, limit } = creditsUsed(quota);

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

      <div className="relative w-full overflow-hidden rounded-2xl bg-background-secondary-default">
        <div aria-hidden className="absolute -top-[11px] left-[328px] size-[277px]">
          <PlanArtFlame src={planArtSrc} className="size-full object-cover" />
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(closest-side at center, rgba(247,247,247,0) 13%, rgba(247,247,247,0.13) 37%, rgba(247,247,247,0.85) 86%, rgba(247,247,247,1) 100%)",
            }}
          />
        </div>

        <div className="relative flex flex-col gap-2.5 py-3 pr-2.5 pl-3">
          <div className="flex flex-col gap-2">
            <span className="inline-flex w-fit items-center rounded-md bg-background-tertiary-default px-1.5 py-0.5 text-body-2-medium text-text-secondary">
              Current plan
            </span>
            <div className="flex flex-col gap-0.5">
              <p className="text-headline-medium text-text-primary">{planHeadline(quota)}</p>
              <p className="text-body-2-regular text-text-secondary">
                {loading
                  ? "Loading usage…"
                  : `${used.toLocaleString()} of ${limit.toLocaleString()} credits used`}
              </p>
            </div>
          </div>
          <Button
            variant="secondary"
            size="small"
            className="w-fit"
            onClick={() => {
              window.location.assign("/pricing");
            }}
          >
            Upgrade
          </Button>
        </div>
      </div>

      <SettingsCard>
        <SettingsRow
          label="Limits"
          description={
            loading
              ? "Loading credit balance…"
              : `${Math.max(limit - used, 0).toLocaleString()} credits remaining`
          }
        >
          <Button variant="secondary" size="small" onClick={onManageLimits}>
            Manage limits
          </Button>
        </SettingsRow>
      </SettingsCard>

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Agent defaults</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Autonomy"
            description="Ask before sensitive tools, or run them automatically"
          >
            <Select
              aria-label="Autonomy"
              selectedKey={autonomyMode}
              onSelectionChange={(key) => {
                if (key !== "manual" && key !== "auto") return;
                setAutonomyMode(key);
                void persist({ autonomyMode: key });
              }}
              triggerClassName={SELECT_TRIGGER}
            >
              <SelectItem id="manual">Manual</SelectItem>
              <SelectItem id="auto">Auto</SelectItem>
            </Select>
          </SettingsRow>
          <SettingsRow
            label="Open artifacts"
            description="Where generated files and links should open"
          >
            <Select
              aria-label="Open artifacts"
              selectedKey={artifactOpenMode}
              onSelectionChange={(key) => {
                if (key !== "in_app" && key !== "browser") return;
                setArtifactOpenMode(key);
                void persist({ artifactOpenMode: key });
              }}
              triggerClassName={SELECT_TRIGGER}
            >
              <SelectItem id="in_app">Inside CoComputer</SelectItem>
              <SelectItem id="browser">In the browser</SelectItem>
            </Select>
          </SettingsRow>
        </SettingsCard>
      </div>

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Notifications</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Critical requests"
            description="Get notified when the agent needs a critical decision"
          >
            <Switch
              aria-label="Critical requests"
              isSelected={toggles.critical}
              onChange={(value) => {
                const next = { ...toggles, critical: value };
                setToggles(next);
                void persist({ notifications: next });
              }}
            />
          </SettingsRow>
          <SettingsRow
            label="System notifications"
            description="Show a notification when an agent completes a task"
          >
            <Switch
              aria-label="System notifications"
              isSelected={toggles.system}
              onChange={(value) => {
                const next = { ...toggles, system: value };
                setToggles(next);
                void persist({ notifications: next });
              }}
            />
          </SettingsRow>
          <SettingsRow
            label="Completion sound"
            description="Play a sound when a task is completed"
          >
            <Switch
              aria-label="Completion sound"
              isSelected={toggles.sound}
              onChange={(value) => {
                const next = { ...toggles, sound: value };
                setToggles(next);
                void persist({ notifications: next });
              }}
            />
          </SettingsRow>
        </SettingsCard>
      </div>
    </div>
  );
}
