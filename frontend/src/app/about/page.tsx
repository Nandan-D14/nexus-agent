/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Cpu, Shield, Terminal } from "lucide-react";
import { MarketingShell } from "@/components/marketing/marketing-shell";
import { MarketingHeroPanel } from "@/components/marketing/marketing-hero-panel";

export const metadata: Metadata = {
  title: "About — CoComputer",
  description:
    "CoComputer gives an agent a real Linux computer in the browser — chat, live desktop, and the connectors you opt in.",
};

const principles = [
  {
    icon: Terminal,
    title: "Real environments",
    body: "Agents should work where work actually happens — a full Linux desktop, not a chat box alone.",
  },
  {
    icon: Shield,
    title: "Isolation by default",
    body: "Every session boots in a sandboxed cloud environment so experimentation stays contained.",
  },
  {
    icon: Cpu,
    title: "Bring your own intelligence",
    body: "Connect the models and tools you trust. CoComputer orchestrates the desktop; you keep control of keys and providers.",
  },
];

export default function AboutPage() {
  return (
    <MarketingShell>
      <main>
        <section className="relative pt-28 pb-12 px-6">
          <div className="max-w-5xl mx-auto">
            <MarketingHeroPanel>
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-100/80 mb-4">
                Company
              </p>
              <h1 className="font-serif text-3xl md:text-5xl text-white mb-6 leading-[1.15]">
                Give an agent a real computer
              </h1>
              <p className="text-blue-100 text-lg leading-relaxed max-w-2xl mx-auto text-balance">
                CoComputer is a cloud workspace from nandan-d14: chat on
                one side, an isolated Linux desktop on the other. The agent can
                see the screen, run the terminal, browse, and use the tools you
                connect — not just another chatbot.
              </p>
            </MarketingHeroPanel>
          </div>
        </section>

        <section className="py-12 px-6">
          <div className="max-w-3xl mx-auto space-y-6 text-muted-foreground leading-relaxed">
            <h2 className="font-serif text-2xl tracking-tight text-foreground">
              Our story
            </h2>
            <p>
              Modern AI can draft text and code, but most work still lives in
              browsers, terminals, files, and tools. CoComputer gives agents a
              secure desktop they can see and operate — with sessions,
              sandboxes, and the integrations you choose.
            </p>
            <p>
              We build for people who want autonomy without giving up control:
              transparent pricing, BYOK model routing, and environments that
              reset cleanly when the job is done.
            </p>
          </div>
        </section>

        <section className="py-12 px-6">
          <div className="max-w-6xl mx-auto">
            <h2 className="mb-10 text-center font-serif text-2xl tracking-tight text-foreground">
              What we believe
            </h2>
            <div className="grid md:grid-cols-3 gap-6">
              {principles.map((item) => (
                <div
                  key={item.title}
                  className="rounded-2xl border border-zinc-100 dark:border-card-border bg-zinc-50/50 dark:bg-zinc-900/30 p-6"
                >
                  <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mb-4">
                    <item.icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2">
                    {item.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {item.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="py-16 px-6">
          <div className="max-w-3xl mx-auto text-center rounded-2xl border border-zinc-100 dark:border-card-border bg-zinc-50/80 dark:bg-zinc-900/40 px-8 py-12">
            <h2 className="mb-3 font-serif text-2xl tracking-tight text-foreground">
              Want to work with us?
            </h2>
            <p className="text-muted-foreground mb-6">
              Whether you are exploring Pro, need Enterprise, or just have a
              question — we would like to hear from you.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Link
                href="/contact"
                className="px-5 py-2.5 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
              >
                Contact us
              </Link>
              <Link
                href="/pricing"
                className="px-5 py-2.5 rounded-full border border-zinc-200 dark:border-card-border text-sm font-medium text-foreground hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors"
              >
                View pricing
              </Link>
            </div>
          </div>
        </section>
      </main>
    </MarketingShell>
  );
}
