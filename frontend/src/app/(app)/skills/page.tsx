"use client";

import { motion } from "framer-motion";
import { Bot, Plus, Search, Zap } from "lucide-react";

export default function SkillsPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 pb-20 pt-4 text-foreground md:px-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white md:text-5xl">
            Agent Skills
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400 md:text-base">
            Manage and discover specialized capabilities for your autonomous agents.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center gap-2 rounded-full bg-zinc-950 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-cyan-700 dark:bg-white dark:text-zinc-950 dark:hover:bg-cyan-200"
        >
          <Plus className="h-4 w-4" />
          Add New Skill
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Placeholder for Skill Cards */}
        {[
          {
            name: "Web Browser",
            description: "Navigate websites, click buttons, and extract information from the web.",
            status: "Active",
            icon: Search,
          },
          {
            name: "Data Analyst",
            description: "Process complex datasets and generate visual reports autonomously.",
            status: "Ready",
            icon: Zap,
          },
          {
            name: "System Control",
            description: "Direct interaction with operating system primitives and shell environments.",
            status: "Core",
            icon: Bot,
          },
        ].map((skill, index) => (
          <motion.div
            key={skill.name}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="group rounded-[28px] border border-zinc-200/80 bg-white/80 p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)] backdrop-blur-sm transition-all hover:border-cyan-500/30 hover:shadow-xl dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none"
          >
            <div className="flex items-start justify-between">
              <div className="rounded-2xl bg-cyan-100 p-3 dark:bg-cyan-500/10">
                <skill.icon className="h-6 w-6 text-cyan-600 dark:text-cyan-400" />
              </div>
              <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:bg-emerald-500/12 dark:text-emerald-300">
                {skill.status}
              </span>
            </div>
            <div className="mt-6">
              <h3 className="text-xl font-semibold text-zinc-950 dark:text-white">
                {skill.name}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
                {skill.description}
              </p>
            </div>
            <div className="mt-6 flex gap-3">
              <button className="flex-1 rounded-full border border-zinc-200 px-4 py-2 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-50 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/5">
                Configure
              </button>
              <button className="flex-1 rounded-full border border-zinc-200 px-4 py-2 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-50 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/5">
                Documentation
              </button>
            </div>
          </motion.div>
        ))}
      </div>

      <section className="rounded-[32px] border border-zinc-200/80 bg-white/85 p-8 shadow-[0_24px_60px_rgba(15,23,42,0.06)] backdrop-blur-sm dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none">
        <div className="flex flex-col gap-6 md:flex-row md:items-center">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-zinc-950 dark:bg-white">
            <Bot className="h-8 w-8 text-white dark:text-zinc-950" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
              Expand your Agent's potential
            </h2>
            <p className="mt-1 text-zinc-500 dark:text-zinc-400">
              New skills can be added via the MCP (Model Context Protocol) to give your agent access to more tools and data sources.
            </p>
          </div>
          <button className="ml-auto rounded-full bg-cyan-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-cyan-700">
            Browse Market
          </button>
        </div>
      </section>
    </div>
  );
}
