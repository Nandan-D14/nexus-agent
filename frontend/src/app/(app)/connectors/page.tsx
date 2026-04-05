"use client";

import { 
  Github, 
  Slack, 
  Files, 
  FileText, 
  Table, 
  Mail, 
  Calendar, 
  MessageSquare, 
  Video, 
  Database,
  Cloud,
  Box,
  Layout,
  Layers
} from "lucide-react";
import { motion } from "framer-motion";

const CONNECTORS = [
  { 
    name: "Google Drive", 
    description: "Access and manage your cloud files directly from Nexus.", 
    icon: Cloud, 
    color: "text-blue-500", 
    bg: "bg-blue-500/10" 
  },
  { 
    name: "GitHub", 
    description: "Manage repositories, pull requests, and issues.", 
    icon: Github, 
    color: "text-zinc-900 dark:text-zinc-100", 
    bg: "bg-zinc-500/10" 
  },
  { 
    name: "Google Sheets", 
    description: "Automate spreadsheet data entry and analysis.", 
    icon: Table, 
    color: "text-emerald-500", 
    bg: "bg-emerald-500/10" 
  },
  { 
    name: "Google Docs", 
    description: "Read, write, and edit documents with ease.", 
    icon: FileText, 
    color: "text-blue-600", 
    bg: "bg-blue-600/10" 
  },
  { 
    name: "Slack", 
    description: "Send messages and monitor channels in real-time.", 
    icon: Slack, 
    color: "text-purple-500", 
    bg: "bg-purple-500/10" 
  },
  { 
    name: "Notion", 
    description: "Sync your workspace pages and databases.", 
    icon: Layout, 
    color: "text-zinc-800 dark:text-zinc-200", 
    bg: "bg-zinc-500/10" 
  },
  { 
    name: "Gmail", 
    description: "Read and compose emails with intelligent context.", 
    icon: Mail, 
    color: "text-red-500", 
    bg: "bg-red-500/10" 
  },
  { 
    name: "Jira", 
    description: "Track projects and manage agile workflows.", 
    icon: Layers, 
    color: "text-blue-400", 
    bg: "bg-blue-400/10" 
  },
  { 
    name: "Trello", 
    description: "Organize tasks and boards collaboratively.", 
    icon: Box, 
    color: "text-sky-500", 
    bg: "bg-sky-500/10" 
  },
  { 
    name: "Zoom", 
    description: "Schedule and join virtual meetings instantly.", 
    icon: Video, 
    color: "text-blue-500", 
    bg: "bg-blue-500/10" 
  },
  { 
    name: "Salesforce", 
    description: "Access CRM data and manage customer relationships.", 
    icon: Cloud, 
    color: "text-sky-600", 
    bg: "bg-sky-600/10" 
  },
  { 
    name: "HubSpot", 
    description: "Sync marketing, sales, and service data.", 
    icon: Database, 
    color: "text-orange-500", 
    bg: "bg-orange-500/10" 
  },
];

export default function ConnectorsPage() {
  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 pb-20">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-500 text-xs font-bold uppercase tracking-widest">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            Coming Soon
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            Connectors
          </h1>
          <p className="text-sm text-zinc-500 max-w-2xl">
            Seamlessly integrate co-computer with your favorite tools and workflows. 
            Native connectors allow the agent to securely access your data across different platforms.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {CONNECTORS.map((connector, i) => (
          <motion.div
            key={connector.name}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="group relative p-6 rounded-3xl bg-white dark:bg-[#111114] border border-zinc-200 dark:border-[#2f2f35] hover:border-blue-500/50 transition-all duration-300 shadow-sm"
          >
            <div className={`w-12 h-12 rounded-2xl ${connector.bg} flex items-center justify-center mb-4 transition-transform group-hover:scale-110 duration-300`}>
              <connector.icon className={`w-6 h-6 ${connector.color}`} />
            </div>
            <h3 className="font-bold text-zinc-900 dark:text-zinc-100 mb-1 tracking-tight">
              {connector.name}
            </h3>
            <p className="text-xs text-zinc-500 leading-relaxed">
              {connector.description}
            </p>
            <div className="absolute top-4 right-4">
              <div className="text-[9px] font-bold uppercase tracking-widest text-zinc-300 dark:text-zinc-700">
                Inactive
              </div>
            </div>
          </motion.div>
        ))}

        {/* Custom Connector Placeholder */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: CONNECTORS.length * 0.05 }}
          className="group p-6 rounded-3xl border border-dashed border-zinc-200 dark:border-[#2f2f35] flex flex-col items-center justify-center text-center gap-3 hover:bg-zinc-50 dark:hover:bg-white/5 transition-colors cursor-pointer"
        >
          <div className="w-10 h-10 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-zinc-400">
            <Files className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-zinc-600 dark:text-zinc-400">Request Integration</h3>
            <p className="text-[10px] text-zinc-400">Don&apos;t see what you need? Let us know.</p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
