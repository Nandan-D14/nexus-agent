/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Plus, Search, Trash2 } from "lucide-react";
import { AnimatePresence } from "framer-motion";

import { SkillCreateSheet } from "./skill-create-sheet";
import { SkillImportModal } from "./skill-import-modal";
import { SkillLibraryPanel } from "./skill-library-panel";
import { skillCategoryIcon } from "./skill-category-icon";
import { PillTab, PillTabList } from "@/components/base/tabs/pill-tab";
import { skillPath } from "@/lib/app-paths";
import {
  downloadSkillExport,
  fetchSkill,
  useDeleteSkillMutation,
  useSkillsQuery,
  useToggleSkillMutation,
  type AgentSkill,
} from "@/lib/queries/skills";
import { queryKeys } from "@/lib/query-keys";
import { cx } from "@/utils/cx";

type SkillsTab = "installed" | "library";

export function SkillsView() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: skills = [], isLoading: loading, error: queryError } = useSkillsQuery();
  const toggleMutation = useToggleSkillMutation();
  const deleteMutation = useDeleteSkillMutation();
  const [tab, setTab] = useState<SkillsTab>("installed");
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");

  const categories = useMemo(() => {
    const values = new Set(skills.map((skill) => skill.category).filter(Boolean));
    return ["all", ...Array.from(values).sort()];
  }, [skills]);

  const filteredSkills = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skills.filter((skill) => {
      if (category !== "all" && skill.category !== category) return false;
      if (!needle) return true;
      return [skill.name, skill.category, skill.description, skill.trigger]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [category, query, skills]);

  const displayError = error || (queryError instanceof Error ? queryError.message : "");

  async function toggleSkill(skill: AgentSkill) {
    setSavingId(skill.skill_id);
    setError("");
    try {
      await toggleMutation.mutateAsync(skill);
    } catch {
      setError("Failed to update skill");
    } finally {
      setSavingId("");
    }
  }

  async function deleteSkill(skill: AgentSkill) {
    if (!confirm("Are you sure you want to delete this skill?")) return;
    setSavingId(skill.skill_id);
    setError("");
    try {
      await deleteMutation.mutateAsync(skill);
    } catch {
      setError("Failed to delete skill");
    } finally {
      setSavingId("");
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 p-6 pb-32 md:p-12">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="font-serif text-3xl leading-none tracking-tight text-text-primary sm:text-4xl">Skills</h1>
          <p className="text-sm text-text-secondary">
            Reusable playbooks in Agent Skills format. Browse open-source libraries or write your own.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          New skill
        </button>
      </div>

      <PillTabList className="w-fit rounded-full bg-background-secondary-default p-0.5">
        <PillTab variant="gray" isSelected={tab === "installed"} onSelect={() => setTab("installed")}>
          Installed
        </PillTab>
        <PillTab variant="gray" isSelected={tab === "library"} onSelect={() => setTab("library")}>
          Open source library
        </PillTab>
      </PillTabList>

      {displayError ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{displayError}</div>
      ) : null}

      {tab === "library" ? (
        <SkillLibraryPanel onOpenImport={() => setShowImport(true)} />
      ) : (
        <div className="space-y-5">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search installed skills…"
                className="w-full rounded-lg border border-input-border bg-input-bg py-2 pl-10 pr-10 text-sm text-text-primary outline-none placeholder:text-text-placeholder focus:border-border-button-hover"
              />
              {loading ? <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-text-tertiary" /> : null}
            </div>
          </div>
          {categories.length > 2 ? (
            <div className="flex flex-wrap gap-2">
              {categories.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setCategory(item)}
                  className={cx(
                    "rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors",
                    category === item
                      ? "bg-foreground text-background"
                      : "bg-background-secondary-default text-text-secondary hover:text-text-primary",
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          ) : null}

          {filteredSkills.length === 0 ? (
            <p className="py-12 text-sm text-text-tertiary">
              {query.trim() || category !== "all" ? "No skills match your filters." : "No skills yet. Create one or add from the library."}
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredSkills.map((skill) => {
                const Icon = skillCategoryIcon(skill.category);
                const href = skillPath(skill.skill_id);
                const fileCount = skill.resources?.length ?? 0;
                return (
                  <div
                    key={skill.skill_id}
                    className="group relative flex flex-col gap-4 rounded-xl border border-card-border bg-background-secondary-default p-5 transition-colors hover:border-border-button-hover"
                  >
                    <Link
                      href={href}
                      aria-label={`Open ${skill.name}`}
                      className="absolute inset-0 z-0 rounded-xl"
                      onMouseEnter={() => {
                        void queryClient.prefetchQuery({
                          queryKey: queryKeys.skill(skill.skill_id),
                          queryFn: () => fetchSkill(skill.skill_id),
                        });
                      }}
                    />
                    <div className="relative z-10 flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-card-border bg-background-tertiary-default text-text-secondary">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <h2 className="text-sm font-medium text-text-primary">{skill.name}</h2>
                          <p className="text-[11px] font-medium uppercase tracking-wider text-text-tertiary">{skill.category}</p>
                        </div>
                      </div>
                      <div className={`mt-1.5 h-2 w-2 rounded-full ${skill.enabled ? "bg-emerald-500" : "bg-background-tertiary-default"}`} />
                    </div>
                    <p className="relative z-10 line-clamp-2 text-sm leading-relaxed text-text-secondary">{skill.description}</p>
                    {skill.trigger ? (
                      <div className="relative z-10 mt-auto border-t border-separator-border pt-4 text-[12px] text-text-tertiary">
                        <span className="font-medium text-text-secondary">Trigger:</span> {skill.trigger}
                      </div>
                    ) : null}
                    {fileCount > 0 ? (
                      <p className="relative z-10 text-[11px] text-text-tertiary">
                        {fileCount} resource{fileCount === 1 ? "" : "s"}
                      </p>
                    ) : null}
                    <div className="relative z-10 flex items-center justify-between pt-1">
                      <span className="text-[11px] font-medium uppercase tracking-tighter text-text-tertiary">
                        {skill.source === "built_in" ? "System" : "User"}
                        {skill.format === "agent_skill" ? " · Agent Skill" : ""}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            void downloadSkillExport(skill.skill_id).catch(() => setError("Failed to export skill"));
                          }}
                          className="rounded-md p-1.5 text-text-tertiary transition-colors hover:text-text-primary"
                          aria-label={`Export ${skill.name}`}
                        >
                          <Download className="h-4 w-4" />
                        </button>
                        {skill.source === "user" ? (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              void deleteSkill(skill);
                            }}
                            className="rounded-md p-1.5 text-text-tertiary transition-colors hover:text-red-400"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            void toggleSkill(skill);
                          }}
                          disabled={savingId === skill.skill_id}
                          className={cx(
                            "rounded-md px-3 py-1.5 text-xs font-semibold transition-all",
                            skill.enabled
                              ? "bg-background-tertiary-default text-text-primary hover:bg-background-secondary-hover"
                              : "bg-foreground text-background",
                          )}
                        >
                          {savingId === skill.skill_id ? "…" : skill.enabled ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      <AnimatePresence>
        {showCreate ? (
          <SkillCreateSheet
            onClose={() => setShowCreate(false)}
            onCreated={(skill) => {
              setShowCreate(false);
              router.push(skillPath(skill.skill_id));
            }}
          />
        ) : null}
        {showImport ? (
          <SkillImportModal
            onClose={() => setShowImport(false)}
            onImported={(skill) => {
              setShowImport(false);
              setTab("installed");
              router.push(skillPath(skill.skill_id));
            }}
          />
        ) : null}
      </AnimatePresence>
    </div>
  );
}
