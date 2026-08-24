/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { WorkflowTemplateData } from "@/lib/message-types";

export type TemplateFilterId = "all" | "with_inputs" | "no_inputs" | "recently_used";

export const TEMPLATE_FILTERS: Array<{ id: TemplateFilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "with_inputs", label: "With inputs" },
  { id: "no_inputs", label: "No inputs" },
  { id: "recently_used", label: "Recently used" },
];

const TITLE_CLIP = 72;

export function templateInputCount(template: WorkflowTemplateData): number {
  return template.input_fields?.length ?? 0;
}

/** Missing status is treated as published so older saved rows still run. */
export function isPublishedTemplate(template: WorkflowTemplateData): boolean {
  return template.status !== "draft";
}

export function filterTemplates(
  templates: WorkflowTemplateData[],
  filter: TemplateFilterId,
): WorkflowTemplateData[] {
  if (filter === "all") return templates;
  return templates.filter((template) => {
    const inputs = templateInputCount(template);
    if (filter === "with_inputs") return inputs > 0;
    if (filter === "no_inputs") return inputs === 0;
    return Boolean(template.last_used_at);
  });
}

export function searchTemplates(
  templates: WorkflowTemplateData[],
  query: string,
): WorkflowTemplateData[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return templates;

  return templates.filter((template) => {
    const haystacks = [
      template.name,
      template.description,
      template.instructions,
      template.source_session_id,
      ...(template.input_fields ?? []).flatMap((field) => [field.key, field.label]),
    ];
    return haystacks.some((value) => value?.toLowerCase().includes(needle));
  });
}

function softenTemplateText(value: string | null | undefined): string {
  return (value ?? "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function clipTemplateText(value: string, max = TITLE_CLIP): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max).trimEnd()}…`;
}

function isSamePreview(left: string, right: string): boolean {
  if (!left || !right) return false;
  if (left === right) return true;
  return left.startsWith(right) || right.startsWith(left);
}

export function templateDisplayTitle(template: Pick<WorkflowTemplateData, "name" | "description">): string {
  const name = softenTemplateText(template.name);
  if (name) return name;
  const description = softenTemplateText(template.description);
  if (description) return clipTemplateText(description);
  return "Untitled template";
}

export function templateDisplayDescription(
  template: Pick<WorkflowTemplateData, "name" | "description" | "instructions">,
): string {
  const title = templateDisplayTitle(template);
  const description = softenTemplateText(template.description);
  if (description && !isSamePreview(description, title)) return description;
  const instructions = softenTemplateText(template.instructions);
  if (instructions && !isSamePreview(instructions, title)) return instructions;
  return "";
}

export function formatTemplateDate(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
