/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { type ChangeEvent, type FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Plus,
  Search,
  Trash2,
  Download,
  Upload,
  X,
  Save,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { skillCategoryIcon } from "@/components/skills/skill-category-icon";
import { skillPath } from "@/lib/app-paths";
import {
  fetchSkill,
  downloadSkillExport,
  useCreateSkillMutation,
  useDeleteSkillMutation,
  useImportSkillMutation,
  useSkillsQuery,
  useToggleSkillMutation,
  type AgentSkill,
} from "@/lib/queries/skills";
import { queryKeys } from "@/lib/query-keys";

export default function SkillsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: skills = [], isLoading: loading, error: queryError } = useSkillsQuery();
  const toggleMutation = useToggleSkillMutation();
  const deleteMutation = useDeleteSkillMutation();
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [query, setQuery] = useState("");

  const filteredSkills = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return skills;
    return skills.filter((skill) =>
      [skill.name, skill.category, skill.description, skill.trigger]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [query, skills]);

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
    <div className="mx-auto max-w-6xl p-6 md:p-12 space-y-10 pb-32">
      {/* Simple Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="font-serif text-3xl leading-none tracking-tight text-white sm:text-4xl">Skills</h1>
          <p className="text-sm text-zinc-500">Reusable playbooks in Agent Skills format. Import SKILL.md from Cursor, Claude, or Codex.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowImport(true)}
            className="border border-zinc-700 hover:border-zinc-500 text-zinc-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
          >
            <Upload className="w-4 h-4" />
            Import SKILL.md
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="bg-white hover:bg-zinc-200 text-black text-sm font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Skill
          </button>
        </div>
      </div>

      {displayError && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-lg text-sm">
          {displayError}
        </div>
      )}

      {/* Clean Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search skills..."
          className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg pl-10 pr-10 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-600 transition-colors"
        />
        {loading ? <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-zinc-500" /> : null}
      </div>

      {filteredSkills.length === 0 ? (
        <p className="text-sm text-zinc-500">
          {query.trim() ? "No skills match your search." : "No skills yet."}
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
                className="group relative flex flex-col gap-4 rounded-xl border border-zinc-800 bg-[#161618] p-5 transition-colors hover:border-zinc-600"
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
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <h2 className="text-sm font-medium text-zinc-200 group-hover:text-white">{skill.name}</h2>
                      <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{skill.category}</p>
                    </div>
                  </div>
                  <div className={`mt-1.5 h-2 w-2 rounded-full ${skill.enabled ? "bg-emerald-500" : "bg-zinc-700"}`} />
                </div>

                <p className="relative z-10 line-clamp-2 text-sm leading-relaxed text-zinc-400">{skill.description}</p>

                {skill.trigger ? (
                  <div className="relative z-10 mt-auto border-t border-zinc-800/50 pt-4 text-[12px] text-zinc-500">
                    <span className="font-medium text-zinc-600">Trigger:</span> {skill.trigger}
                  </div>
                ) : null}

                {fileCount > 0 ? (
                  <p className="relative z-10 text-[11px] text-zinc-600">
                    {fileCount} resource{fileCount === 1 ? "" : "s"}
                  </p>
                ) : null}

                <div className="relative z-10 flex items-center justify-between pt-2">
                  <span className="text-[11px] font-medium uppercase tracking-tighter text-zinc-600">
                    {skill.source === "built_in" ? "System" : "User"}
                    {skill.format === "agent_skill" ? " · Agent Skill" : ""}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        void downloadSkillExport(skill.skill_id).catch(() => setError("Failed to export skill"));
                      }}
                      className="p-1.5 text-zinc-600 transition-colors hover:text-zinc-300"
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
                        className="p-1.5 text-zinc-600 transition-colors hover:text-red-400"
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
                      className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                        skill.enabled
                          ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                          : "bg-zinc-100 text-black hover:bg-white"
                      }`}
                    >
                      {savingId === skill.skill_id ? "..." : skill.enabled ? "Disable" : "Enable"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <AnimatePresence>
        {showCreate && (
          <CreateSkillModal
            onClose={() => setShowCreate(false)}
            onCreated={(skill) => {
              setShowCreate(false);
              router.push(skillPath(skill.skill_id));
            }}
          />
        )}
        {showImport && (
          <ImportSkillModal
            onClose={() => setShowImport(false)}
            onImported={(skill) => {
              setShowImport(false);
              router.push(skillPath(skill.skill_id));
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function CreateSkillModal({
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

  async function submit(event: FormEvent) {
    event.preventDefault();
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
        className="relative w-full max-w-2xl bg-[#1a1a1c] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col"
      >
        <div className="h-14 border-b border-zinc-800/50 flex items-center justify-between px-6 bg-black/20">
           <h2 className="text-sm font-bold text-white uppercase tracking-widest">New Skill</h2>
           <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
             <X className="w-4 h-4" />
           </button>
        </div>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <form onSubmit={submit} className="space-y-6">
            {error && (
              <div className="p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-400">
                {error}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Name" value={name} onChange={setName} placeholder="e.g. Data Analyzer" />
              <Field label="Category" value={category} onChange={setCategory} placeholder="e.g. Research" />
            </div>
            
            <Field label="Trigger" value={trigger} onChange={setTrigger} placeholder="When task involves..." />
            <Field label="Description" value={description} onChange={setDescription} placeholder="Briefly describe module logic..." />
            <TextArea label="Instructions" value={instructions} onChange={setInstructions} placeholder="Define constraints, detailed steps, and examples..." />

            <button
              disabled={saving}
              className="w-full bg-white hover:bg-zinc-200 text-black font-bold py-3 rounded-lg flex items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50 text-sm"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Skill
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}

function ImportSkillModal({
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
        className="relative w-full max-w-2xl bg-[#1a1a1c] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col"
      >
        <div className="h-14 border-b border-zinc-800/50 flex items-center justify-between px-6 bg-black/20">
          <h2 className="text-sm font-bold text-white uppercase tracking-widest">Import SKILL.md</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <form onSubmit={submit} className="space-y-6">
            {error ? (
              <div className="p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-400">{error}</div>
            ) : null}
            <p className="text-sm text-zinc-500">
              Paste a SKILL.md, upload a skill folder zip (SKILL.md + scripts/references), or import from a public GitHub URL. Compatible with Cursor, Claude Code, and Codex.
            </p>
            <Field label="GitHub or raw URL" value={sourceUrl} onChange={setSourceUrl} placeholder="https://github.com/org/repo/blob/main/skills/pdf-processing/SKILL.md" />
            <div className="space-y-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500 px-0.5">Or upload SKILL.md / .zip</span>
              <input
                type="file"
                accept=".md,.zip,text/markdown,text/plain,application/zip"
                onChange={(event) => void onPickFile(event)}
                className="block w-full text-xs text-zinc-400 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-200"
              />
              {zipName ? <p className="text-xs text-zinc-500">Package: {zipName}</p> : null}
            </div>
            <TextArea label="SKILL.md" value={skillMd} onChange={setSkillMd} placeholder={"---\nname: my-skill\ndescription: When to use this skill\n---\n\n# Instructions"} />
            <button
              disabled={saving || (!skillMd.trim() && !sourceUrl.trim() && !zipB64)}
              className="w-full bg-white hover:bg-zinc-200 text-black font-bold py-3 rounded-lg flex items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50 text-sm"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              Import
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <div className="space-y-1.5">
      <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500 px-0.5">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-600 transition-colors placeholder:text-zinc-700"
      />
    </div>
  );
}

function TextArea({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <div className="space-y-1.5">
      <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500 px-0.5">{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={6}
        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-600 transition-colors placeholder:text-zinc-700 resize-none custom-scrollbar"
      />
    </div>
  );
}
