/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import {
  Bot,
  MessagesSquare,
  Clock,
  GitBranch,
  Plug,
  PlusCircle,
  Sparkles,
  Search,
  Library,
  Settings2,
} from "lucide-react";

export const NAV_LINKS = [
  { name: "Chat Console", href: "/dashboard", icon: MessagesSquare },
  { name: "History", href: "/history", icon: Clock },
  { name: "Agent Workflow", href: "/templates", icon: GitBranch },
  { name: "Agent Skills", href: "/skills", icon: Sparkles },
  { name: "Connectors", href: "/connectors", icon: Plug },
  { name: "Settings", href: "/settings", icon: Settings2 },
] as const;

export const SIDEBAR_ACTIONS = [
  { name: "New task", icon: PlusCircle, href: "/session/new" },
  { name: "Agent", icon: Bot, href: "/agent" },
  { name: "Search", icon: Search, href: "/search" },
  { name: "Library", icon: Library, href: "/library" },
] as const;

export default NAV_LINKS;
