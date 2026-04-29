import {
  MessageSquare,
  History,
  Workflow,
  Cable,
  PlusCircle,
  Bot,
  Search,
  Library,
  Settings,
} from "lucide-react";

export const NAV_LINKS = [
  { name: "Chat Console", href: "/dashboard", icon: MessageSquare },
  { name: "History", href: "/history", icon: History },
  { name: "Agent Workflow", href: "/templates", icon: Workflow },
  { name: "Connectors", href: "/connectors", icon: Cable },
  { name: "Settings", href: "/settings", icon: Settings },
] as const;

export const SIDEBAR_ACTIONS = [
  { name: "New task", icon: PlusCircle, href: "/session/new" },
  { name: "Agent", icon: Bot, href: "/agent" },
  { name: "Search", icon: Search, href: "/search" },
  { name: "Library", icon: Library, href: "/library" },
] as const;

export default NAV_LINKS;
