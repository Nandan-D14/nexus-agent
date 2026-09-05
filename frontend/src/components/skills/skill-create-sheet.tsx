/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { type FormEvent, useMemo, useState } from "react";
import { Loader2, Save, X } from "lucide-react";
import { motion } from "framer-motion";

import { SkillField, SkillTextArea } from "./skill-fields";
import { renderSkillMdPreview, skillSpecErrors, slugifySkillName } from "./skill-md-preview";
import { useCreateSkillMutation, type AgentSkill } from "@/lib/queries/skills";

export function SkillCreateSheet({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (skill: AgentSkill) => void | Promise<void>;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Custom");
  const [description, setDescription] = useState("");
  const [trigger, setTrigger] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const createMutation = useCreateSkillMutation();

  const specErrors = useMemo(
    () => skillSpecErrors({ name, description, instructions }),
    [name, description, instructions],
  );
  const preview = useMemo(
    () => renderSkillMdPreview({ name, category, description, trigger, instructions }),
    [name, category, description, trigger, instructions],
  );
  const slug = slugifySkillName(name);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (specErrors.length) {
      setError(specErrors[0] ?? "Fix the SKILL.md spec errors first.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const created = await createMutation.mutateAsync({
        name,
        category,
        description,
        trigger,
        instructions,
        enabled: true,
      });
      await onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create skill");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.98, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 10 }}
        className="relative flex max-h-[min(880px,calc(100dvh-32px))] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-card-border bg-background-primary-default shadow-2xl"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-separator-border px-6">
          <h2 className="text-sm font-semibold text-text-primary">New skill</h2>
          <button type="button" onClick={onClose} className="text-text-tertiary transition-colors hover:text-text-primary">
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={submit} className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-2">
          <div className="custom-scrollbar space-y-5 overflow-y-auto p-6">
            {error ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</div>
            ) : null}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <SkillField
                label="Name"
                value={name}
                onChange={setName}
                placeholder="e.g. Data Analyzer"
                hint={slug ? `SKILL.md name: ${slug}` : "Becomes a kebab-case id"}
              />
              <SkillField label="Category" value={category} onChange={setCategory} placeholder="e.g. Research" />
            </div>
            <SkillField label="Trigger" value={trigger} onChange={setTrigger} placeholder="When the task involves…" />
            <SkillTextArea
              label="Description"
              value={description}
              onChange={setDescription}
              placeholder="What it does and when the agent should use it"
              rows={3}
            />
            <SkillTextArea
              label="Instructions"
              value={instructions}
              onChange={setInstructions}
              placeholder="Steps, constraints, and examples…"
              rows={8}
            />
            {specErrors.length ? (
              <ul className="space-y-1 text-[12px] text-text-tertiary">
                {specErrors.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-text-tertiary">Matches the Agent Skills SKILL.md spec.</p>
            )}
            <button
              type="submit"
              disabled={saving || specErrors.length > 0}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save skill
            </button>
          </div>
          <div className="hidden min-h-0 flex-col border-l border-separator-border bg-background-secondary-default md:flex">
            <p className="shrink-0 border-b border-separator-border px-5 py-3 font-mono text-[11px] uppercase tracking-wider text-text-tertiary">
              SKILL.md preview
            </p>
            <pre className="custom-scrollbar min-h-0 flex-1 overflow-auto px-5 py-4 font-mono text-[12px] leading-relaxed text-text-secondary whitespace-pre-wrap">
              {preview}
            </pre>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
