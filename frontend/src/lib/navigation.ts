import {
  MessageSquare,
  Monitor,
  Workflow,
  FolderOpen,
  PlusCircle,
  Bot,
  Search,
  Library,
  Settings,
} from "lucide-react";

export const NAV_LINKS = [
  { name: "Chat Console", href: "/dashboard", icon: MessageSquare },
  { name: "Live Desktop", href: "/history", icon: Monitor },
  { name: "Agent Workflow", href: "/templates", icon: Workflow },
  { name: "Context Packets", href: "/connectors", icon: FolderOpen },
  { name: "Settings", href: "/settings", icon: Settings },
] as const;

export const SIDEBAR_ACTIONS = [
  { name: "New task", icon: PlusCircle, href: "/session/new" },
  { name: "Agent", icon: Bot, href: "/agent" },
  { name: "Search", icon: Search, href: "/search" },
  { name: "Library", icon: Library, href: "/library" },
] as const;

export default NAV_LINKS;
