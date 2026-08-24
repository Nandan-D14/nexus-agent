"use client";

import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

export function SettingsAppearance() {
  return (
    <div className="flex w-full flex-col gap-6">
      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Theme</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Appearance"
            description="Switch between light and dark mode"
          >
            <ThemeToggle appearance="segmented" />
          </SettingsRow>
        </SettingsCard>
      </div>
    </div>
  );
}
