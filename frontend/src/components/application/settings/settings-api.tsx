"use client";

import { useEffect, useState } from "react";
import { RiCheckboxCircleFill, RiKey2Line } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Chip } from "@/components/base/badges/chip";
import { Input } from "@/components/base/input/input";
import { useSettings } from "@/lib/settings-context";
import {
  type GeminiProvider,
  type UserSettingsResponse,
  type UserSettingsUpdatePayload,
  fetchUserSettings,
  updateUserSettings,
} from "@/lib/user-settings";
import { cx } from "@/utils/cx";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

/**
 * API & Keys settings page — BYOK keys, shared access code, and Gemini
 * provider selection. Loads/saves via user-settings; restyled into BoardUI
 * SettingsCard / SettingsRow chrome.
 */

export function SettingsApi({ onSaved }: { onSaved?: () => void } = {}) {
  const { refreshBetaStatus } = useSettings();
  const [settings, setSettings] = useState<UserSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accessCode, setAccessCode] = useState("");
  const [e2bApiKey, setE2bApiKey] = useState("");
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [geminiProvider, setGeminiProvider] = useState<GeminiProvider>("apiKey");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchUserSettings()
      .then((data) => {
        if (cancelled) return;
        setSettings(data);
        setGeminiProvider(data.byok.geminiProvider || "apiKey");
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

  const sharedE2bReady = Boolean(settings?.byok.sharedAccessEnabled && settings.byok.serverE2bConfigured);
  const sharedVertexReady = Boolean(settings?.byok.sharedAccessEnabled && settings.byok.vertexConfigured);
  const e2bReady = Boolean(settings?.byok.e2bKeySet || sharedE2bReady);
  const geminiReady = Boolean(
    settings && (geminiProvider === "vertex" ? sharedVertexReady : settings.byok.geminiKeySet),
  );

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const payload: UserSettingsUpdatePayload = { byok: { geminiProvider } };
      if (e2bApiKey.trim()) payload.byok!.e2bApiKey = e2bApiKey.trim();
      if (geminiProvider === "apiKey" && geminiApiKey.trim()) {
        payload.byok!.geminiApiKey = geminiApiKey.trim();
      }
      if (accessCode.trim()) payload.byok!.accessCode = accessCode.trim();

      const updated = await updateUserSettings(payload);
      setSettings(updated);
      setAccessCode("");
      setE2bApiKey("");
      setGeminiApiKey("");
      onSaved?.();
      void refreshBetaStatus();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex w-full items-center justify-center py-16">
        <span className="text-body-2-regular text-text-secondary">Loading…</span>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      {error && (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {error}
        </div>
      )}

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>API Access</SettingsSectionLabel>
        <SettingsCard>
          {settings?.byok.sharedAccessCodeConfigured && (
            <SettingsRow
              label="Shared Access Code"
              description="Enter the shared code to use server-provided keys"
            >
              <Input
                size="small"
                type="password"
                aria-label="Shared Access Code"
                value={accessCode}
                onChange={setAccessCode}
                placeholder="Enter access code"
                className="w-[202px] shrink-0"
              />
            </SettingsRow>
          )}

          <SettingsRow label="E2B API Key" description="Powers the agent sandbox runtime">
            <div className="flex shrink-0 items-center gap-2">
              {e2bReady && (
                <Chip variant="caption" color="lime" className="inline-flex items-center gap-0.5">
                  <RiCheckboxCircleFill className="size-3" aria-hidden />
                  Ready
                </Chip>
              )}
              <Input
                size="small"
                type="password"
                aria-label="E2B API Key"
                leadingIcon={RiKey2Line}
                value={e2bApiKey}
                onChange={setE2bApiKey}
                placeholder={settings?.byok.e2bKeySet ? "••••••••••••••••" : "Enter E2B key"}
                className="w-[202px] shrink-0"
              />
            </div>
          </SettingsRow>
        </SettingsCard>
      </div>

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Gemini Configuration</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Provider"
            description="Direct API key or Google Vertex AI"
          >
            <div className="flex shrink-0 items-center gap-2">
              {geminiReady && (
                <Chip variant="caption" color="lime" className="inline-flex items-center gap-0.5">
                  <RiCheckboxCircleFill className="size-3" aria-hidden />
                  Ready
                </Chip>
              )}
              <div className="flex rounded-lg border border-border-button-default bg-background-primary-default p-0.5 shadow-xs">
                {(
                  [
                    { id: "apiKey" as const, label: "API Key" },
                    { id: "vertex" as const, label: "Vertex AI" },
                  ] as const
                ).map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setGeminiProvider(option.id)}
                    className={cx(
                      "h-7 rounded-md px-2 text-body-2-medium transition-colors duration-150 ease",
                      "outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                      geminiProvider === option.id
                        ? "bg-background-tertiary-default text-text-primary"
                        : "text-text-secondary hover:text-text-primary",
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </SettingsRow>

          {geminiProvider === "apiKey" && (
            <SettingsRow label="Gemini API Key" description="Used when provider is Direct API Key">
              <Input
                size="small"
                type="password"
                aria-label="Gemini API Key"
                leadingIcon={RiKey2Line}
                value={geminiApiKey}
                onChange={setGeminiApiKey}
                placeholder={settings?.byok.geminiKeySet ? "••••••••••••••••" : "Enter Gemini API Key"}
                className="w-[202px] shrink-0"
              />
            </SettingsRow>
          )}
        </SettingsCard>
      </div>

      <Button
        variant="primary"
        size="small"
        className="w-fit"
        disabled={saving || !settings}
        onClick={() => void handleSave()}
      >
        {saving ? "Saving…" : "Save API Settings"}
      </Button>
    </div>
  );
}
