"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/base/buttons/button";
import {
  type UserSettingsResponse,
  fetchUserSettings,
  updateUserSettings,
} from "@/lib/user-settings";
import { cx } from "@/utils/cx";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

/**
 * Voice settings page — agent voice picker and speaking rate. Loads/saves
 * via user-settings; restyled into BoardUI SettingsCard chrome.
 */

const VOICES = [
  { id: "Puck", name: "Puck" },
  { id: "Charon", name: "Charon" },
  { id: "Kore", name: "Kore" },
  { id: "Fenrir", name: "Fenrir" },
] as const;

export function SettingsVoice({ onSaved }: { onSaved?: () => void } = {}) {
  const [settings, setSettings] = useState<UserSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voiceId, setVoiceId] = useState("Puck");
  const [speed, setSpeed] = useState(1.0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchUserSettings()
      .then((data) => {
        if (cancelled) return;
        setSettings(data);
        const voice = (data.settings.voice as { voiceId?: string; speed?: number } | undefined) || {};
        setVoiceId(voice.voiceId || "Puck");
        setSpeed(voice.speed ?? 1.0);
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

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateUserSettings({
        settings: { ...settings?.settings, voice: { voiceId, speed } },
      });
      setSettings(updated);
      onSaved?.();
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
        <SettingsSectionLabel>Voice</SettingsSectionLabel>
        <SettingsCard>
          <div className="flex w-full flex-col gap-2 py-2.5 pr-2.5">
            <p className="text-body-regular text-text-primary">Agent voice</p>
            <p className="text-body-2-regular text-text-secondary">
              Choose how the agent sounds during voice interactions
            </p>
            <div className="mt-1 grid grid-cols-2 gap-1.5">
              {VOICES.map((voice) => (
                <button
                  key={voice.id}
                  type="button"
                  onClick={() => setVoiceId(voice.id)}
                  className={cx(
                    "rounded-2lg border px-3 py-2 text-left text-body-medium transition-colors duration-150 ease",
                    "outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                    voiceId === voice.id
                      ? "border-border-button-default bg-background-tertiary-default text-text-primary"
                      : "border-separator-border bg-transparent text-text-secondary hover:bg-background-secondary-hover/60 hover:text-text-primary",
                  )}
                >
                  {voice.name}
                </button>
              ))}
            </div>
          </div>
        </SettingsCard>
      </div>

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Speaking Rate</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow label="Playback speed" description="Slow ← → Fast">
            <div className="flex w-[202px] shrink-0 items-center gap-2">
              <input
                type="range"
                min={0.5}
                max={2.0}
                step={0.1}
                value={speed}
                onChange={(e) => setSpeed(parseFloat(e.target.value))}
                aria-label="Speaking rate"
                className="h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-background-tertiary-default accent-text-primary"
              />
              <span className="w-8 shrink-0 text-right text-body-2-medium text-text-primary">
                {speed.toFixed(1)}x
              </span>
            </div>
          </SettingsRow>
        </SettingsCard>
      </div>

      <Button
        variant="primary"
        size="small"
        className="w-fit"
        disabled={saving || !settings}
        onClick={() => void handleSave()}
      >
        {saving ? "Saving…" : "Save Voice Settings"}
      </Button>
    </div>
  );
}
