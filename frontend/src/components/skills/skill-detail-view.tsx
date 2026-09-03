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

function buildFallbackSkillMd(skill: AgentSkill): string {
  const q = (v: string) => JSON.stringify(v);
  const lines: string[] = ["---", `name: ${skill.skill_id}`, `description: ${q(skill.description || skill.trigger || skill.name)}`];
  if (skill.license) lines.push(`license: ${q(skill.license)}`);
  if (skill.compatibility) lines.push(`compatibility: ${q(skill.compatibility)}`);
  if (skill.allowed_tools) lines.push(`allowed-tools: ${skill.allowed_tools}`);
  const meta: string[] = [];
  if (skill.trigger) meta.push(`  cocomputer.trigger: ${q(skill.trigger)}`);
  if (skill.category) meta.push(`  cocomputer.category: ${q(skill.category)}`);
  if (skill.sandbox_path) meta.push(`  cocomputer.sandbox_path: ${q(skill.sandbox_path)}`);
  if (meta.length) {
    lines.push("metadata:");
    lines.push(...meta);
  }
  lines.push("---", "");
  const body = (skill.instructions || skill.description || "").trim();
  if (body) lines.push(body);
  // add helpful note for built-ins that have no bundled files
  if (!skill.resources?.length && !skill.files) {
    // keep body as-is, frontmatter already shows full context
  }
  return lines.join("\n");
}

function viewerEntries(skill: AgentSkill): { path: string; content: string }[] {
  const files = { ...(skill.files ?? {}) };
  let skillMd = files[SKILL_MD];
  if (!skillMd?.trim()) {
    skillMd = buildFallbackSkillMd(skill);
    // ensure placeholder detection sees real content
    if (!skill.instructions?.trim() && skill.description) skillMd += `\n\n${skill.description}`;
  }
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
      <p className="text-sm text-text-tertiary">
        This file is listed on the skill but its contents are not stored. Export the skill to
        download the package.
      </p>
    );
  }
  // SKILL.md full context: render YAML frontmatter as code + body as markdown for visibility
  if (path === SKILL_MD && content.trim().startsWith("---")) {
    const parts = content.split("\n---");
    // content is "---\nname: ...\n---\n\nbody"
    if (parts.length >= 2) {
      const frontmatterRaw = parts[0].replace(/^---\s*\n/, "").trim();
      const bodyRaw = parts.slice(1).join("\n---").replace(/^\s*\n/, "").trim();
      const yamlBlock = frontmatterRaw ? `\`\`\`yaml\n${frontmatterRaw}\n\`\`\`` : "";
      const combined = [yamlBlock, bodyRaw].filter(Boolean).join("\n\n");
      return (
        <div className="text-text-primary">
          <ChatMarkdown content={combined} />
        </div>
      );
    }
  }
  const markdown = isMarkdownPath(path)
    ? content
    : langFromPath(path)
      ? `\`\`\`${langFromPath(path)}\n${content}\n\`\`\``
      : `\`\`\`\n${content}\n\`\`\``;
  return (
    <div className="text-text-primary">
      <ChatMarkdown content={markdown} />
    </div>
  );
}

type SkillDetailViewProps = {
  skillId: string;
};

export function SkillDetailView({ skillId }: SkillDetailViewProps) {
  const router = useRouter();
  const { data: skill, isLoading, isFetching, error, refetch } = useSkillQuery(skillId);
  const toggleMutation = useToggleSkillMutation();
  const deleteMutation = useDeleteSkillMutation();
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [activePath, setActivePath] = useState(SKILL_MD);

  const entries = useMemo(() => (skill ? viewerEntries(skill) : []), [skill]);
  const showRail = entries.length > 1;
  // Full-context: when placeholder has no file bodies, fall back to instructions so SKILL.md is never empty
  const hasPlaceholderOnly = Boolean(skill && !skill.files && entries.length === 1 && !entries[0]?.content.trim());
  const isInitialLoading = isLoading && !skill;
  const isPlaceholderLoading = Boolean(skill && hasPlaceholderOnly && isFetching);

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

  if (isInitialLoading || isPlaceholderLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-8 p-6 pb-16 md:p-12">
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 p-8">
          <Loader2 className="h-6 w-6 animate-spin text-text-tertiary" />
          <p className="text-sm text-text-tertiary">Loading skill context…</p>
        </div>
      </div>
    );
  }

  if (!skill) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6 md:p-12">
        <Link href={APP_SKILLS} className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
          <ArrowLeft className="h-4 w-4" />
          Back to skills
        </Link>
        <p className="text-sm text-text-secondary">
          {error instanceof Error ? error.message : "This skill could not be found."}
        </p>
        {error ? (
          <button
            type="button"
            onClick={() => void refetch()}
            className="rounded-lg border border-border-button-default px-4 py-2 text-sm text-text-primary hover:border-border-button-hover"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  }

  const Icon = skillCategoryIcon(skill.category);
  const displayError = actionError || (error instanceof Error ? error.message : "");

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6 pb-16 md:p-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-4">
          <Link href={APP_SKILLS} className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
            <ArrowLeft className="h-4 w-4" />
            Back to skills
          </Link>
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-card-border bg-background-secondary-default text-text-secondary">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-serif text-3xl leading-none tracking-tight text-text-primary">{skill.name}</h1>
                <span className={`mt-1 h-2 w-2 rounded-full ${skill.enabled ? "bg-emerald-500" : "bg-background-tertiary-default"}`} />
              </div>
              <p className="mt-1 text-[11px] font-medium uppercase tracking-wider text-text-tertiary">
                {skill.category}
                <span className="text-text-tertiary">
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
            className="inline-flex items-center gap-2 rounded-lg border border-border-button-default px-3 py-2 text-sm font-medium text-text-primary hover:border-border-button-hover"
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
              className="inline-flex items-center gap-2 rounded-lg border border-border-button-default px-3 py-2 text-sm font-medium text-text-secondary hover:border-red-500/40 hover:text-red-400"
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
                ? "bg-background-secondary-default text-text-primary hover:bg-background-secondary-hover"
                : "bg-foreground text-background"
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

      <div className="space-y-3 text-sm leading-relaxed text-text-secondary">
        {skill.trigger ? (
          <p>
            <span className="font-medium text-text-tertiary">Trigger: </span>
            {skill.trigger}
          </p>
        ) : null}
        {skill.description ? <p>{skill.description}</p> : null}
        <div className="flex flex-wrap gap-2 pt-1">
          {skill.sandbox_path ? (
            <span className="inline-flex items-center rounded-md border border-card-border bg-background-secondary-default px-2.5 py-1 font-mono text-xs text-text-secondary">
              {skill.sandbox_path}
            </span>
          ) : null}
          {skill.allowed_tools ? (
            <span className="inline-flex items-center rounded-md border border-card-border bg-background-secondary-default px-2.5 py-1 text-xs text-text-secondary">
              Tools: {skill.allowed_tools}
            </span>
          ) : null}
          {skill.compatibility ? (
            <span className="inline-flex items-center rounded-md border border-card-border bg-background-secondary-default px-2.5 py-1 text-xs text-text-secondary">
              {skill.compatibility}
            </span>
          ) : null}
        </div>
        {skill.license ? (
          <p className="text-xs text-text-tertiary">License: {skill.license}</p>
        ) : null}
      </div>

      {/* Full skill context — every file visible without hidden rail clipping */}
      <div className={showRail ? "grid min-w-0 gap-6 md:grid-cols-[200px_minmax(0,1fr)]" : "min-w-0"}>
        {showRail ? (
          <nav className="flex flex-col gap-1 self-start md:sticky md:top-6" aria-label="Skill files">
            <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-widest text-text-tertiary">
              Files · {entries.length}
            </p>
            {entries.map((entry) => (
              <button
                key={entry.path}
                type="button"
                onClick={() => {
                  setActivePath(entry.path);
                  document.getElementById(`skill-file-${entry.path}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                className={`rounded-lg px-3 py-2 text-left font-mono text-xs transition-colors ${
                  activePath === entry.path
                    ? "bg-background-secondary-hover text-text-primary"
                    : "text-text-tertiary hover:bg-background-secondary-default hover:text-text-primary"
                }`}
              >
                {entry.path}
                {entry.content.trim() ? "" : " · empty"}
              </button>
            ))}
          </nav>
        ) : null}
        <div className="min-w-0 space-y-6">
          {entries.map((entry) => (
            <section
              key={entry.path}
              id={`skill-file-${entry.path}`}
              className="min-w-0 overflow-hidden scroll-mt-6 rounded-xl border border-card-border bg-background-secondary-default"
            >
              <div className="flex items-center justify-between border-b border-separator-border bg-background-tertiary-default/40 px-5 py-3">
                <p className="font-mono text-[11px] uppercase tracking-wider text-text-secondary">{entry.path}</p>
                <span className="text-[11px] text-text-tertiary">{entry.content.length} chars</span>
              </div>
              <div className="min-w-0 p-5 md:p-6">
                <FilePreview path={entry.path} content={entry.content} />
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
