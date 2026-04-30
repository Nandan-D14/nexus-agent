"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Code2,
  FileText,
  Loader2,
  Monitor,
  Plus,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  X,
  Save,
  type LucideIcon,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { authenticatedFetch, parseApiError } from "@/lib/api-client";

type AgentSkill = {
  skill_id: string;
  name: string;
  category: string;
  description: string;
  trigger: string;
  instructions: string;
  source: "built_in" | "user";
  enabled: boolean;
};

const categoryIcons: Record<string, LucideIcon> = {
  Research: Search,
  Browser: Search,
  Coding: Code2,
  Developer: Code2,
  System: Settings2,
  Computer: Monitor,
  Documents: FileText,
  Files: FileText,
  Custom: Sparkles,
};

function iconFor(category: string) {
  return categoryIcons[category] ?? BookOpen;
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [query, setQuery] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await authenticatedFetch("/api/v1/skills");
      if (!response.ok) throw new Error(await parseApiError(response));
      const body = (await response.json()) as { skills?: AgentSkill[] };
      setSkills(body.skills ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

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

  async function toggleSkill(skill: AgentSkill) {
    setSavingId(skill.skill_id);
    try {
      const response = await authenticatedFetch(`/api/v1/skills/${skill.skill_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !skill.enabled }),
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      await load();
    } catch {
      setError("Failed to update skill");
    } finally {
      setSavingId("");
    }
  }

  async function deleteSkill(skill: AgentSkill) {
    if (!confirm("Are you sure you want to delete this skill?")) return;
    setSavingId(skill.skill_id);
    try {
      const response = await authenticatedFetch(`/api/v1/skills/${skill.skill_id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      await load();
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
          <h1 className="text-2xl font-semibold text-white">Skills</h1>
          <p className="text-sm text-zinc-500">Manage agent instructions and capabilities.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-white hover:bg-zinc-200 text-black text-sm font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Skill
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-lg text-sm">
          {error}
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

      {/* Skills Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredSkills.map((skill) => {
          const Icon = iconFor(skill.category);
          return (
            <div
              key={skill.skill_id}
              className="bg-[#161618] border border-zinc-800 rounded-xl p-5 flex flex-col gap-4 hover:border-zinc-700 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-400">
                    <Icon className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className="text-sm font-medium text-zinc-200">{skill.name}</h2>
                    <p className="text-[11px] text-zinc-500 font-medium uppercase tracking-wider">{skill.category}</p>
                  </div>
                </div>
                <div className={`w-2 h-2 rounded-full mt-1.5 ${skill.enabled ? "bg-emerald-500" : "bg-zinc-700"}`} />
              </div>
              
              <p className="text-sm text-zinc-400 line-clamp-2 leading-relaxed">
                {skill.description}
              </p>

              {skill.trigger && (
                <div className="text-[12px] text-zinc-500 border-t border-zinc-800/50 pt-4 mt-auto">
                  <span className="text-zinc-600 font-medium">Trigger:</span> {skill.trigger}
                </div>
              )}

              <div className="flex items-center justify-between pt-2">
                <span className="text-[11px] text-zinc-600 font-medium uppercase tracking-tighter">
                  {skill.source === "built_in" ? "System" : "User"}
                </span>
                <div className="flex items-center gap-2">
                  {skill.source === "user" && (
                    <button
                      onClick={() => void deleteSkill(skill)}
                      className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => void toggleSkill(skill)}
                    disabled={savingId === skill.skill_id}
                    className={`text-xs font-semibold px-3 py-1.5 rounded-md transition-all ${
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

      <AnimatePresence>
        {showCreate && (
          <CreateSkillModal
            onClose={() => setShowCreate(false)}
            onCreated={async () => {
              setShowCreate(false);
              await load();
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
  onCreated: () => void | Promise<void>;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Custom");
  const [description, setDescription] = useState("");
  const [trigger, setTrigger] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await authenticatedFetch("/api/v1/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, category, description, trigger, instructions, enabled: true }),
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      await onCreated();
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
