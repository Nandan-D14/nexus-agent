"use client";

import { useEffect, useState } from "react";
import { Switch } from "@/components/base/switch/switch";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

type AgentSkill = {
  skill_id: string;
  name: string;
  category: string;
  description: string;
  enabled: boolean;
  source: "built_in" | "user";
};

export function SettingsSkills() {
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authenticatedFetch("/api/v1/skills");
      if (!response.ok) throw new Error(await parseApiError(response));
      const body = (await response.json()) as { skills?: AgentSkill[] };
      setSkills(body.skills ?? []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load skills.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggleSkill = async (skill: AgentSkill) => {
    setSavingId(skill.skill_id);
    setError(null);
    try {
      const response = await authenticatedFetch(`/api/v1/skills/${skill.skill_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !skill.enabled }),
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      setSkills((prev) =>
        prev.map((item) =>
          item.skill_id === skill.skill_id ? { ...item, enabled: !item.enabled } : item,
        ),
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update skill.");
    } finally {
      setSavingId("");
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
