"use client";

import { useState } from "react";
import { Switch } from "@/components/base/switch/switch";
import { skillPath } from "@/lib/app-paths";
import { useSkillsQuery, useToggleSkillMutation } from "@/lib/queries/skills";
import { useSettings } from "@/lib/settings-context";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

export function SettingsSkills() {
  const { data: skills = [], isLoading: loading, error: queryError } = useSkillsQuery();
  const toggleMutation = useToggleSkillMutation();
  const { setIsSettingsOpen } = useSettings();
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const toggleSkill = async (skill: (typeof skills)[number]) => {
    setSavingId(skill.skill_id);
    setError(null);
    try {
      await toggleMutation.mutateAsync(skill);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update skill.");
    } finally {
      setSavingId("");
    }
  };

  const displayError = error || (queryError instanceof Error ? queryError.message : null);

  return (
    <div className="flex w-full flex-col gap-6">
      {displayError ? (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {displayError}
        </div>
      ) : null}

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Agent skills</SettingsSectionLabel>
        <SettingsCard>
          {loading ? (
            <div className="py-6 pr-2.5 text-body-2-regular text-text-secondary">Loading…</div>
          ) : skills.length === 0 ? (
            <div className="py-6 pr-2.5 text-body-2-regular text-text-secondary">
              No skills configured.
            </div>
          ) : (
            skills.map((skill) => (
              <SettingsRow
                key={skill.skill_id}
                label={skill.name}
                description={skill.description || skill.category}
                href={skillPath(skill.skill_id)}
                onNavigate={() => setIsSettingsOpen(false)}
              >
                <Switch
                  aria-label={`Enable ${skill.name}`}
                  isSelected={skill.enabled}
                  isDisabled={savingId === skill.skill_id}
                  onChange={() => void toggleSkill(skill)}
                />
              </SettingsRow>
            ))
          )}
        </SettingsCard>
      </div>
    </div>
  );
}
