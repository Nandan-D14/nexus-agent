/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiJson, authenticatedFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { queryKeys } from "@/lib/query-keys";

export type AgentSkill = {
  skill_id: string;
  name: string;
  category: string;
  description: string;
  trigger: string;
  instructions: string;
  source: "built_in" | "user";
  enabled: boolean;
  format?: "legacy" | "agent_skill";
  resources?: string[];
  sandbox_path?: string;
  files?: Record<string, string>;
  license?: string;
  compatibility?: string;
  allowed_tools?: string;
};

export type CreateSkillPayload = {
  name: string;
  category: string;
  description: string;
  trigger: string;
  instructions: string;
  enabled: boolean;
};

export type ImportSkillPayload = {
  skill_md?: string;
  source_url?: string;
  files?: Record<string, string>;
  zip_b64?: string;
  enabled?: boolean;
};

export type SkillCatalogSource = {
  id: string;
  label: string;
  repo: string;
};

export type SkillCatalogItem = {
  id: string;
  name: string;
  description: string;
  license: string;
  source: string;
  source_label: string;
  source_url: string;
  html_url: string;
  restricted: boolean;
  category?: string;
  installed: boolean;
};

export type SkillCatalogResponse = {
  sources: SkillCatalogSource[];
  skills: SkillCatalogItem[];
  error?: string | null;
};

export async function fetchSkills(): Promise<AgentSkill[]> {
  const body = await apiJson<{ skills?: AgentSkill[] }>("/api/v1/skills");
  return body.skills ?? [];
}

export async function fetchSkill(skillId: string): Promise<AgentSkill> {
  const body = await apiJson<{ skill?: AgentSkill }>(
    `/api/v1/skills/${encodeURIComponent(skillId)}`,
  );
  if (!body.skill) {
    throw new Error("Skill not found");
  }
  return body.skill;
}

export function useSkillsQuery() {
  const { user, isLoading: authLoading } = useAuth();
  return useQuery({
    queryKey: queryKeys.skills(),
    queryFn: fetchSkills,
    enabled: Boolean(!authLoading && user),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useSkillQuery(skillId: string) {
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const placeholder = queryClient
    .getQueryData<AgentSkill[]>(queryKeys.skills())
    ?.find((skill) => skill.skill_id === skillId);

  return useQuery({
    queryKey: queryKeys.skill(skillId),
    queryFn: () => fetchSkill(skillId),
    enabled: Boolean(!authLoading && user && skillId),
    placeholderData: placeholder as AgentSkill | undefined,
    staleTime: 30_000,
    retry: 1,
  });
}

export function useToggleSkillMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (skill: AgentSkill) => {
      await apiJson(`/api/v1/skills/${encodeURIComponent(skill.skill_id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !skill.enabled }),
      });
    },
    onMutate: async (skill) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.skills() });
      const previous = queryClient.getQueryData<AgentSkill[]>(queryKeys.skills());
      const previousDetail = queryClient.getQueryData<AgentSkill>(queryKeys.skill(skill.skill_id));
      queryClient.setQueryData<AgentSkill[]>(queryKeys.skills(), (current) =>
        (current ?? []).map((item) =>
          item.skill_id === skill.skill_id ? { ...item, enabled: !item.enabled } : item,
        ),
      );
      queryClient.setQueryData<AgentSkill>(queryKeys.skill(skill.skill_id), (current) =>
        current ? { ...current, enabled: !skill.enabled } : current,
      );
      return { previous, previousDetail };
    },
    onError: (_error, skill, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.skills(), context.previous);
      }
      if (context?.previousDetail) {
        queryClient.setQueryData(queryKeys.skill(skill.skill_id), context.previousDetail);
      }
    },
    onSettled: (_data, _error, skill) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.skills() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.skill(skill.skill_id) });
    },
  });
}

export function useDeleteSkillMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (skill: AgentSkill) => {
      await apiJson(`/api/v1/skills/${encodeURIComponent(skill.skill_id)}`, {
        method: "DELETE",
      });
    },
    onSuccess: (_data, skill) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.skills() });
      queryClient.removeQueries({ queryKey: queryKeys.skill(skill.skill_id) });
    },
  });
}

function unwrapSkill(body: AgentSkill | { skill?: AgentSkill } | null | undefined): AgentSkill {
  if (body && "skill_id" in body && body.skill_id) {
    return body;
  }
  const skill = body && "skill" in body ? body.skill : undefined;
  if (!skill?.skill_id) {
    throw new Error("Skill response was missing");
  }
  return skill;
}

export function useCreateSkillMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CreateSkillPayload) => {
      const body = await apiJson<AgentSkill | { skill?: AgentSkill }>("/api/v1/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return unwrapSkill(body);
    },
    onSuccess: (skill) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.skills() });
      queryClient.setQueryData(queryKeys.skill(skill.skill_id), skill);
    },
  });
}

export function useImportSkillMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ImportSkillPayload) => {
      const body = await apiJson<{ skill?: AgentSkill }>("/api/v1/skills/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return unwrapSkill(body);
    },
    onSuccess: (skill) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.skills() });
      void queryClient.invalidateQueries({ queryKey: ["skills", "catalog"] });
      queryClient.setQueryData(queryKeys.skill(skill.skill_id), skill);
    },
  });
}

export async function fetchSkillCatalog(source = ""): Promise<SkillCatalogResponse> {
  const params = source.trim() ? `?source=${encodeURIComponent(source.trim())}` : "";
  const body = await apiJson<SkillCatalogResponse>(`/api/v1/skills/catalog${params}`);
  return {
    sources: body.sources ?? [],
    skills: body.skills ?? [],
    error: body.error ?? null,
  };
}

export function useSkillCatalogQuery(source: string, enabled = true) {
  const { user, isLoading: authLoading } = useAuth();
  const key = source.trim() || "defaults";
  return useQuery({
    queryKey: queryKeys.skillsCatalog(key),
    queryFn: () => fetchSkillCatalog(source),
    enabled: Boolean(!authLoading && user && enabled),
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

export async function downloadSkillExport(skillId: string) {
  const response = await authenticatedFetch(`/api/v1/skills/${encodeURIComponent(skillId)}/export`);
  if (!response.ok) {
    throw new Error("Failed to export skill");
  }
  const blob = await response.blob();
  const header = response.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(header);
  const filename = match?.[1] || `${skillId}-SKILL.md`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
