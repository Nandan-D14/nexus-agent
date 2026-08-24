/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useParams } from "next/navigation";

import { SkillDetailView } from "@/components/skills/skill-detail-view";

export default function SkillDetailPage() {
  const params = useParams();
  const raw = params.skill_id ?? params.skill_id;
  const skillId = decodeURIComponent(String(Array.isArray(raw) ? raw[0] : raw || ""));
  return <SkillDetailView skillId={skillId} />;
}
