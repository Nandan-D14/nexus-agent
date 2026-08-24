/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Loader2, Trash2 } from "lucide-react";

import { ChatMarkdown } from "@/components/chat-markdown";
import { skillCategoryIcon } from "@/components/skills/skill-category-icon";
import { APP_SKILLS } from "@/lib/app-paths";
import {
  downloadSkillExport,
  useDeleteSkillMutation,
  useSkillQuery,
  useToggleSkillMutation,
  type AgentSkill,
} from "@/lib/queries/skills";

const SKILL_MD = "SKILL.md";

function isMarkdownPath(path: string): boolean {
  const lower = path.toLowerCase();
  return lower === "skill.md" || lower.endsWith(".md") || lower.endsWith(".mdx");
}

function langFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
    py: "python",
    ts: "ts",
    tsx: "tsx",
    js: "javascript",
    json: "json",
    sh: "bash",
    bash: "bash",
    yml: "yaml",
    yaml: "yaml",
    css: "css",
    html: "html",
    toml: "toml",
  };
  return map[ext] || "";
}

function viewerEntries(skill: AgentSkill): { path: string; content: string }[] {
  const files = { ...(skill.files ?? {}) };
  const skillMd = files[SKILL_MD] ?? skill.instructions ?? "";
  delete files[SKILL_MD];
  for (const path of skill.resources ?? []) {
    if (path === SKILL_MD) continue;
    if (!(path in files)) files[path] = "";
  }
  const rest = Object.entries(files).sort(([a], [b]) => a.localeCompare(b));
  return [{ path: SKILL_MD, content: skillMd }, ...rest.map(([path, content]) => ({ path, content }))];
}

function FilePreview({ path, content }: { path: string; content: string }) {
  if (!content.trim()) {
    return (
      <p className="text-sm text-zinc-500">
        This file is listed on the skill but its contents are not stored. Export the skill to
        download the package.
      </p>
    );
  }
  const markdown = isMarkdownPath(path)
    ? content
    : langFromPath(path)
      ? `\`\`\`${langFromPath(path)}\n${content}\n\`\`\``
      : `\`\`\`\n${content}\n\`\`\``;
  return (
    <div className="dark text-zinc-200">
      <ChatMarkdown content={markdown} />
    </div>
  );
}

type SkillDetailViewProps = {
  skillId: string;
};

export function SkillDetailView({ skillId }: SkillDetailViewProps) {
  const router = useRouter();
  const { data: skill, isLoading, error } = useSkillQuery(skillId);
  const toggleMutation = useToggleSkillMutation();
  const deleteMutation = useDeleteSkillMutation();
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [activePath, setActivePath] = useState(SKILL_MD);

  const entries = useMemo(() => (skill ? viewerEntries(skill) : []), [skill]);
  const showRail = entries.length > 1;
  const active = entries.find((entry) => entry.path === activePath) ?? entries[0];

  useEffect(() => {
    setActivePath(SKILL_MD);
  }, [skillId]);

  async function toggleSkill() {
    if (!skill) return;
    setSaving(true);
    setActionError("");
    try {
      await toggleMutation.mutateAsync(skill);
    } catch {
      setActionError("Failed to update skill");
    } finally {
      setSaving(false);
    }
  }

  async function deleteSkill() {
    if (!skill) return;
    if (!confirm("Are you sure you want to delete this skill?")) return;
    setSaving(true);
    setActionError("");
    try {
      await deleteMutation.mutateAsync(skill);
      router.push(APP_SKILLS);
    } catch {
      setActionError("Failed to delete skill");
      setSaving(false);
    }
  }

  if (isLoading && !skill) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (!skill) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6 md:p-12">
        <Link href={APP_SKILLS} className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white">
          <ArrowLeft className="h-4 w-4" />
          Back to skills
        </Link>
        <p className="text-sm text-zinc-400">
          {error instanceof Error ? error.message : "This skill could not be found."}
        </p>
      </div>
    );
  }

  const Icon = skillCategoryIcon(skill.category);
  const displayError = actionError || (error instanceof Error ? error.message : "");

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6 pb-32 md:p-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-4">
          <Link href={APP_SKILLS} className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
            Back to skills
          </Link>
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-serif text-3xl leading-none tracking-tight text-white">{skill.name}</h1>
                <span className={`mt-1 h-2 w-2 rounded-full ${skill.enabled ? "bg-emerald-500" : "bg-zinc-700"}`} />
              </div>
              <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                {skill.category}
                <span className="text-zinc-600">
                  {" "}
                  · {skill.source === "built_in" ? "System" : "User"}
                  {skill.format === "agent_skill" ? " · Agent Skill" : ""}
                </span>
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void downloadSkillExport(skill.skill_id).catch(() => setActionError("Failed to export skill"));
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200 hover:border-zinc-500"
            aria-label={`Export ${skill.name}`}
          >
            <Download className="h-4 w-4" />
            Export
          </button>
          {skill.source === "user" ? (
            <button
              type="button"
              onClick={() => void deleteSkill()}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-400 hover:border-red-500/40 hover:text-red-400"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void toggleSkill()}
            disabled={saving}
            className={`rounded-md px-3 py-2 text-xs font-semibold transition-all ${
              skill.enabled
                ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                : "bg-zinc-100 text-black hover:bg-white"
            }`}
          >
            {saving ? "..." : skill.enabled ? "Disable" : "Enable"}
          </button>
        </div>
      </div>

      {displayError ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {displayError}
        </div>
      ) : null}

      <div className="space-y-3 text-sm leading-relaxed text-zinc-400">
        {skill.trigger ? (
          <p>
            <span className="font-medium text-zinc-500">Trigger: </span>
            {skill.trigger}
          </p>
        ) : null}
        {skill.description ? <p>{skill.description}</p> : null}
        {skill.sandbox_path ? (
          <p className="font-mono text-xs text-zinc-600">{skill.sandbox_path}</p>
        ) : null}
      </div>

      <div className={showRail ? "grid gap-6 md:grid-cols-[200px_minmax(0,1fr)]" : ""}>
        {showRail ? (
          <nav className="flex flex-col gap-1" aria-label="Skill files">
            {entries.map((entry) => (
              <button
                key={entry.path}
                type="button"
                onClick={() => setActivePath(entry.path)}
                className={`rounded-lg px-3 py-2 text-left font-mono text-xs transition-colors ${
                  active?.path === entry.path
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
                }`}
              >
                {entry.path}
              </button>
            ))}
          </nav>
        ) : null}
        <div className="rounded-xl border border-zinc-800 bg-[#161618] p-5 md:p-6">
          {showRail ? (
            <p className="mb-4 font-mono text-[11px] uppercase tracking-wider text-zinc-600">{active?.path}</p>
          ) : (
            <p className="mb-4 text-[11px] font-bold uppercase tracking-widest text-zinc-500">Instructions</p>
          )}
          {active ? <FilePreview path={active.path} content={active.content} /> : null}
        </div>
      </div>
    </div>
  );
}
