/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { type ChangeEvent, type FormEvent, useState } from "react";
import { Loader2, Upload, X } from "lucide-react";
import { motion } from "framer-motion";

import { SkillField, SkillTextArea } from "./skill-fields";
import { useImportSkillMutation, type AgentSkill } from "@/lib/queries/skills";

export function SkillImportModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (skill: AgentSkill) => void | Promise<void>;
}) {
  const [skillMd, setSkillMd] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [zipB64, setZipB64] = useState("");
  const [zipName, setZipName] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const importMutation = useImportSkillMutation();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const imported = await importMutation.mutateAsync({
        skill_md: skillMd.trim() || undefined,
        source_url: sourceUrl.trim() || undefined,
        zip_b64: zipB64 || undefined,
        enabled: true,
      });
      await onImported(imported);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to import skill");
    } finally {
      setSaving(false);
    }
  }

  async function onPickFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.name.toLowerCase().endsWith(".zip")) {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      const chunk = 0x8000;
      for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
      }
      setZipB64(btoa(binary));
      setZipName(file.name);
      setSkillMd("");
      return;
    }
    setZipB64("");
    setZipName("");
    setSkillMd(await file.text());
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
        className="relative flex max-h-[min(760px,calc(100dvh-32px))] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-card-border bg-background-primary-default shadow-2xl"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-separator-border px-6">
          <h2 className="text-sm font-semibold text-text-primary">Import SKILL.md</h2>
          <button type="button" onClick={onClose} className="text-text-tertiary transition-colors hover:text-text-primary">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="custom-scrollbar flex-1 overflow-y-auto p-6">
          <form onSubmit={submit} className="space-y-5">
            {error ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</div>
            ) : null}
            <p className="text-sm text-text-secondary">
              Paste a SKILL.md, upload a skill folder zip, or import from a public GitHub URL.
            </p>
            <SkillField
              label="GitHub or raw URL"
              value={sourceUrl}
              onChange={setSourceUrl}
              placeholder="https://github.com/org/repo/blob/main/skills/pdf-processing/SKILL.md"
            />
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
                Or upload SKILL.md / .zip
              </span>
              <input
                type="file"
                accept=".md,.zip,text/markdown,text/plain,application/zip"
                onChange={(event) => void onPickFile(event)}
                className="block w-full text-xs text-text-secondary file:mr-3 file:rounded-md file:border-0 file:bg-background-secondary-default file:px-3 file:py-1.5 file:text-text-primary"
              />
              {zipName ? <p className="text-xs text-text-tertiary">Package: {zipName}</p> : null}
            </div>
            <SkillTextArea
              label="SKILL.md"
              value={skillMd}
              onChange={setSkillMd}
              placeholder={"---\nname: my-skill\ndescription: When to use this skill\n---\n\n# Instructions"}
              rows={8}
            />
            <button
              type="submit"
              disabled={saving || (!skillMd.trim() && !sourceUrl.trim() && !zipB64)}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              Import
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}
