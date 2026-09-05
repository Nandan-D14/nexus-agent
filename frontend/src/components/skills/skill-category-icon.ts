/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import {
  BookOpen,
  Code2,
  FileText,
  Monitor,
  Search,
  Settings2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  Research: Search,
  Browser: Search,
  Coding: Code2,
  Developer: Code2,
  System: Settings2,
  Computer: Monitor,
  Documents: FileText,
  Files: FileText,
  Analysis: Search,
  Testing: Settings2,
  Tools: Sparkles,
  Productivity: BookOpen,
  Automation: Settings2,
  Design: Sparkles,
  Custom: Sparkles,
};

export function skillCategoryIcon(category: string): LucideIcon {
  return CATEGORY_ICONS[category] ?? BookOpen;
}
