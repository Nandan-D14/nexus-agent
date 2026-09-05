/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

const SKILL_NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function slugifySkillName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

export function skillSpecErrors(input: {
  name: string;
  description: string;
  instructions: string;
}): string[] {
  const errors: string[] = [];
  const slug = slugifySkillName(input.name);
  if (!slug || !SKILL_NAME_RE.test(slug)) {
    errors.push("Name must become a kebab-case id (lowercase letters, numbers, hyphens).");
  }
  if (!input.description.trim()) {
    errors.push("Description is required (when to use this skill).");
  } else if (input.description.trim().length > 1024) {
    errors.push("Description must be 1024 characters or less.");
  }
  if (!input.instructions.trim()) {
    errors.push("Instructions are required.");
  } else if (input.instructions.length > 16000) {
    errors.push("Instructions must be 16000 characters or less.");
  }
  return errors;
}

export function renderSkillMdPreview(input: {
  name: string;
  category: string;
  description: string;
  trigger: string;
  instructions: string;
}): string {
  const name = slugifySkillName(input.name) || "skill";
  const description = (input.description.trim() || input.trigger.trim() || `Use the ${input.name || name} skill.`).slice(0, 1024);
  const lines = ["---", `name: ${name}`, `description: ${yamlQuote(description)}`];
  if (input.trigger.trim() || input.category.trim()) {
    lines.push("metadata:");
    if (input.trigger.trim()) lines.push(`  cocomputer.trigger: ${yamlQuote(input.trigger.trim())}`);
    if (input.category.trim()) lines.push(`  cocomputer.category: ${yamlQuote(input.category.trim())}`);
  }
  lines.push("---", "");
  if (input.instructions.trim()) {
    lines.push(input.instructions.trim());
    lines.push("");
  }
  return lines.join("\n");
}

function yamlQuote(value: string): string {
  if (!value) return '""';
  if (/[:#{}[\],&*?|>!%@`]/.test(value) || value.includes("\n")) {
    return JSON.stringify(value);
  }
  return value;
}
