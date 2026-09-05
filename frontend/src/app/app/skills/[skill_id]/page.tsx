/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useParams } from "next/navigation";

import { SkillDetailView } from "@/components/skills/skill-detail-view";

export default function SkillDetailPage() {
  const params = useParams() as Record<string, string | string[] | undefined>;
  const raw = params.skill_id ?? params.skillId ?? params.id;
  const rawValue = Array.isArray(raw) ? raw[0] : raw || "";
  let skillId = "";
  try {
    skillId = decodeURIComponent(String(rawValue));
  } catch {
    skillId = String(rawValue);
  }
  return <SkillDetailView skillId={skillId} />;
}
