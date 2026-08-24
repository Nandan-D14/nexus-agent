/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";

export function HeroAnnouncement() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7 }}
      className="mb-8 flex justify-center"
    >
      <Link
        href="#features"
        className="group inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-4 py-1.5 text-sm text-zinc-900 shadow-[0_8px_24px_rgba(0,0,0,0.12),inset_0_1px_0_rgba(255,255,255,1)] transition-colors hover:bg-zinc-50 dark:border-white/25 dark:bg-white dark:hover:bg-zinc-100"
      >
        <Sparkles className="size-3.5 fill-amber-400 text-amber-400" aria-hidden />
        <span className="font-medium text-zinc-900">
          Cloud desktop + agent in one workspace
        </span>
        <ArrowRight
          className="size-3.5 text-zinc-500 transition-transform duration-300 ease-in-out group-hover:translate-x-0.5"
          aria-hidden
        />
      </Link>
    </motion.div>
  );
}
