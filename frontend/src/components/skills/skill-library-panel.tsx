/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { type FormEvent, useMemo, useState } from "react";
import { ExternalLink, Loader2, Plus, Search, Upload, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { skillCategoryIcon } from "./skill-category-icon";
import { PillTab, PillTabList } from "@/components/base/tabs/pill-tab";
import { cx } from "@/utils/cx";
import {
  useImportSkillMutation,
  useSkillCatalogQuery,
  type SkillCatalogItem,
} from "@/lib/queries/skills";

export function SkillLibraryPanel({
  onImported,
  onOpenImport,
}: {
  onImported?: () => void;
  onOpenImport: () => void;
}) {
  const [sourceFilter, setSourceFilter] = useState("all");
  const [customSource, setCustomSource] = useState("");
  const [scanInput, setScanInput] = useState("");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<SkillCatalogItem | null>(null);
  const [addingId, setAddingId] = useState("");
  const [error, setError] = useState("");
  const catalogQuery = useSkillCatalogQuery(customSource);
  const importMutation = useImportSkillMutation();

  const skills = catalogQuery.data?.skills ?? [];
  const sources = catalogQuery.data?.sources ?? [
    { id: "anthropics", label: "Anthropic", repo: "anthropics/skills" },
    { id: "vercel", label: "Vercel", repo: "vercel-labs/agent-skills" },
  ];
  const catalogError =
    catalogQuery.error instanceof Error ? catalogQuery.error.message : catalogQuery.data?.error || "";

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skills.filter((skill) => {
      if (!customSource && sourceFilter !== "all" && skill.source !== sourceFilter) return false;
      if (!needle) return true;
      return [skill.name, skill.id, skill.description, skill.source_label, skill.license]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [customSource, query, skills, sourceFilter]);

  async function addSkill(item: SkillCatalogItem) {
    if (item.installed) return;
    setAddingId(item.id);
    setError("");
    try {
      await importMutation.mutateAsync({ source_url: item.source_url, enabled: true });
      setPreview(null);
      onImported?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add skill");
    } finally {
      setAddingId("");
    }
  }

  function scanRepo(event: FormEvent) {
    event.preventDefault();
    setCustomSource(scanInput.trim());
    setSourceFilter("all");
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <PillTabList className="w-fit rounded-full bg-background-secondary-default p-0.5">
          <PillTab variant="gray" isSelected={!customSource && sourceFilter === "all"} onSelect={() => { setCustomSource(""); setSourceFilter("all"); }}>
            All
          </PillTab>
          {sources.map((source) => (
            <PillTab
              key={source.id}
              variant="gray"
              isSelected={!customSource && sourceFilter === source.id}
              onSelect={() => {
                setCustomSource("");
                setSourceFilter(source.id);
              }}
            >
              {source.label}
            </PillTab>
          ))}
        </PillTabList>
        <button
          type="button"
          onClick={onOpenImport}
          className="inline-flex items-center gap-2 rounded-lg border border-border-button-default px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-background-secondary-hover"
        >
          <Upload className="h-4 w-4" />
          Import file or URL
        </button>
      </div>

      <form onSubmit={scanRepo} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={scanInput}
          onChange={(event) => setScanInput(event.target.value)}
          placeholder="Scan a GitHub repo — owner/repo or https://github.com/org/repo"
          className="w-full rounded-lg border border-input-border bg-input-bg px-3.5 py-2 text-sm text-text-primary outline-none placeholder:text-text-placeholder focus:border-border-button-hover"
        />
        <button
          type="submit"
          className="shrink-0 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-40"
          disabled={!scanInput.trim()}
        >
          Scan
        </button>
      </form>

      {customSource ? (
        <p className="text-sm text-text-secondary">
          Showing skills from <span className="font-medium text-text-primary">{customSource}</span>
          {" · "}
          <button type="button" className="text-text-primary underline-offset-2 hover:underline" onClick={() => { setCustomSource(""); setScanInput(""); }}>
            Back to libraries
          </button>
        </p>
      ) : null}

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search the library…"
          className="w-full rounded-lg border border-input-border bg-input-bg py-2 pl-10 pr-3 text-sm text-text-primary outline-none placeholder:text-text-placeholder focus:border-border-button-hover"
        />
      </div>

      {error || catalogError ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error || catalogError}
        </div>
      ) : null}

      {catalogQuery.isLoading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-text-tertiary">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading open-source skills…
        </div>
      ) : filtered.length === 0 ? (
        <p className="py-12 text-sm text-text-tertiary">
          {query.trim() ? "No skills match your search." : "No SKILL.md packages found in this source."}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((skill) => {
            const Icon = skillCategoryIcon(skill.category || "Custom");
            return (
              <article
                key={`${skill.source}:${skill.id}:${skill.source_url}`}
                className="flex flex-col gap-3 rounded-xl border border-card-border bg-background-secondary-default p-5"
              >
                <button type="button" className="flex items-start gap-3 text-left" onClick={() => setPreview(skill)}>
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-card-border bg-background-tertiary-default text-text-secondary">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-text-primary">{skill.name}</span>
                    <span className="text-[11px] uppercase tracking-wider text-text-tertiary">
                      {skill.source_label}
                      {skill.restricted ? " · Source-available" : skill.license ? ` · ${skill.license}` : ""}
                    </span>
                  </span>
                </button>
                <p className="line-clamp-3 text-sm leading-relaxed text-text-secondary">{skill.description}</p>
                <div className="mt-auto flex items-center justify-between pt-1">
                  <button
                    type="button"
                    onClick={() => setPreview(skill)}
                    className="text-xs font-medium text-text-secondary hover:text-text-primary"
                  >
                    Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => void addSkill(skill)}
                    disabled={skill.installed || addingId === skill.id}
                    className={cx(
                      "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                      skill.installed
                        ? "cursor-default bg-background-tertiary-default text-text-tertiary"
                        : "bg-foreground text-background hover:opacity-90 disabled:opacity-40",
                    )}
                  >
                    {addingId === skill.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : skill.installed ? null : <Plus className="h-3.5 w-3.5" />}
                    {skill.installed ? "Added" : "Add"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <AnimatePresence>
        {preview ? (
          <SkillPreviewDrawer
            skill={preview}
            adding={addingId === preview.id}
            onClose={() => setPreview(null)}
            onAdd={() => void addSkill(preview)}
          />
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function SkillPreviewDrawer({
  skill,
  adding,
  onClose,
  onAdd,
}: {
  skill: SkillCatalogItem;
  adding: boolean;
  onClose: () => void;
  onAdd: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[110] flex justify-end">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <motion.aside
        initial={{ x: 24, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 24, opacity: 0 }}
        className="relative flex h-full w-full max-w-md flex-col border-l border-card-border bg-background-primary-default shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-separator-border px-5 py-4">
          <h2 className="text-sm font-semibold text-text-primary">{skill.name}</h2>
          <button type="button" onClick={onClose} className="text-text-tertiary hover:text-text-primary">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto p-5">
          <p className="text-[11px] uppercase tracking-wider text-text-tertiary">
            {skill.source_label}
            {skill.restricted ? " · Source-available" : ""}
            {skill.license ? ` · ${skill.license}` : ""}
          </p>
          <p className="text-sm leading-relaxed text-text-secondary">{skill.description}</p>
          <a
            href={skill.html_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-text-primary hover:underline"
          >
            View on GitHub
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
        <div className="border-t border-separator-border p-5">
          <button
            type="button"
            onClick={onAdd}
            disabled={skill.installed || adding}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-foreground py-2.5 text-sm font-medium text-background disabled:cursor-not-allowed disabled:opacity-40"
          >
            {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {skill.installed ? "Already added" : "Add to my skills"}
          </button>
        </div>
      </motion.aside>
    </div>
  );
}
