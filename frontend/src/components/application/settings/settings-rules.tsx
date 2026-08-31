"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/base/buttons/button";
import { InputPlusMenu } from "@/components/base/input-plus-menu";
import { fetchUserSettings, patchAppSettings, readAppSettings } from "@/lib/user-settings";
import { APP_TEMPLATES } from "@/lib/app-paths";
import { SettingsCard, SettingsSectionLabel } from "./settings-rows";

export function SettingsRules({ onSaved }: { onSaved?: () => void } = {}) {
  const [rules, setRules] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchUserSettings()
      .then((data) => {
        if (!cancelled) setRules(readAppSettings(data).agentRules);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load rules.");
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
      await patchAppSettings({ agentRules: rules });
      onSaved?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save rules.");
    } finally {
      setSaving(false);
    }
  };

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
        <SettingsSectionLabel>Standing instructions</SettingsSectionLabel>
        <SettingsCard className="p-3 pl-3">
          <div className="relative">
            <textarea
              aria-label="Standing instructions"
              value={rules}
              disabled={loading}
              onChange={(event) => setRules(event.target.value)}
              placeholder="Always prefer concise answers. Ask before sending email."
              className="min-h-[140px] w-full resize-y rounded-xl border border-border-button-default bg-background-primary-default px-3 pb-10 pt-2 text-body-regular text-text-primary outline-none placeholder:text-text-tertiary focus-visible:ring-2 focus-visible:ring-border-focus-ring"
            />
            <div className="absolute bottom-2 left-2">
              <InputPlusMenu
                showUpload={false}
                showVoice={false}
                onInsertText={(text) => setRules((prev) => prev + text)}
              />
            </div>
          </div>
        </SettingsCard>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          size="small"
          disabled={saving || loading}
          onClick={() => void handleSave()}
        >
          {saving ? "Saving…" : "Save rules"}
        </Button>
        <Button
          variant="secondary"
          size="small"
          onClick={() => {
            window.location.assign(APP_TEMPLATES);
          }}
        >
          Open templates
        </Button>
      </div>
    </div>
  );
}
