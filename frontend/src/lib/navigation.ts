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
  LayoutGrid,
} from "lucide-react";

import {
  APP_CONNECTORS,
  APP_HISTORY,
  APP_HOME,
  APP_LIBRARY,
  APP_SCHEDULE,
  APP_SETTINGS,
  APP_SKILLS,
  APP_TEMPLATES,
  APP_WORKSPACE,
} from "./app-paths";

export const NAV_LINKS = [
  { name: "Workspace", href: APP_WORKSPACE, icon: LayoutGrid },
  { name: "History", href: APP_HISTORY, icon: MessagesSquare },
  { name: "Schedule task", href: APP_SCHEDULE, icon: Clock },
  { name: "Library", href: APP_LIBRARY, icon: Library },
  { name: "Agent Workflow", href: APP_TEMPLATES, icon: GitBranch },
  { name: "Agent Skills", href: APP_SKILLS, icon: Sparkles },
  { name: "Connectors", href: APP_CONNECTORS, icon: Plug },
  { name: "Settings", href: APP_SETTINGS, icon: Settings2 },
] as const;

export const SIDEBAR_ACTIONS = [
  { name: "New task", icon: PlusCircle, href: APP_HOME },
  { name: "Agent", icon: Bot, href: "/agent" },
  { name: "Search", icon: Search, href: "/search" },
  { name: "Library", icon: Library, href: APP_LIBRARY },
] as const;

export default NAV_LINKS;
