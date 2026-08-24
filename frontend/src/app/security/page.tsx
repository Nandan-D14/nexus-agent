/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import {
  KeyRound,
  Lock,
  Server,
  ShieldCheck,
  EyeOff,
  Bug,
} from "lucide-react";
import { MarketingShell } from "@/components/marketing/marketing-shell";
import { MarketingHeroPanel } from "@/components/marketing/marketing-hero-panel";

export const metadata: Metadata = {
  title: "Security — CoComputer",
  description:
    "How CoComputer protects accounts, sandboxes, and data with isolation, encryption, and responsible disclosure.",
};

const controls = [
  {
    icon: Server,
    title: "Isolated sandboxes",
    body: "Sessions run in fresh cloud environments so workloads stay separated from other customers and from host infrastructure.",
  },
  {
    icon: Lock,
    title: "Encryption in transit",
    body: "Traffic between your browser, our APIs, and session services is protected with TLS.",
  },
  {
    icon: KeyRound,
    title: "Strong authentication",
    body: "Sign-in is handled through trusted identity providers. You control account access and can revoke sessions by signing out.",
  },
  {
    icon: EyeOff,
    title: "BYOK-minded design",
    body: "When you bring your own API keys, treat them as secrets. Rotate keys if they may have been exposed in a session or chat.",
  },
  {
    icon: ShieldCheck,
    title: "Least privilege tooling",
    body: "Agents operate inside the sandbox boundary with plan-based resource limits to reduce blast radius from mistakes or abuse.",
  },
  {
    icon: Bug,
    title: "Responsible disclosure",
    body: "We welcome good-faith reports of vulnerabilities. Contact security@cocomputer.com with clear reproduction steps.",
  },
];

export default function SecurityPage() {
  return (
    <MarketingShell>
      <main>
        <section className="relative pt-28 pb-12 px-6">
          <div className="max-w-5xl mx-auto">
            <MarketingHeroPanel>
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-100/80 mb-4">
                Security
              </p>
              <h1 className="font-serif text-3xl md:text-5xl text-white mb-6 leading-[1.15]">
                Built for powerful agents, contained by design
              </h1>
              <p className="text-blue-100 text-lg leading-relaxed max-w-2xl mx-auto text-balance">
                CoComputer gives AI real desktop capability. Our security
                approach focuses on isolation, authenticated access, and clear
                channels for reporting issues.
              </p>
            </MarketingHeroPanel>
          </div>
        </section>

        <section className="py-8 px-6">
          <div className="max-w-6xl mx-auto grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {controls.map((item) => (
              <div
                key={item.title}
                className="rounded-2xl border border-zinc-100 dark:border-card-border bg-zinc-50/50 dark:bg-zinc-900/30 p-6"
              >
                <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center mb-4">
                  <item.icon className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <h2 className="font-semibold text-foreground mb-2">
                  {item.title}
                </h2>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="py-16 px-6">
          <div className="max-w-3xl mx-auto space-y-6 text-muted-foreground leading-relaxed">
            <h2 className="font-serif text-2xl tracking-tight text-foreground">
              Shared responsibility
            </h2>
            <p>
              Security is a partnership. We operate the platform and sandbox
              boundaries; you are responsible for the software you run inside
              sessions, the data you paste into chats, and the third-party keys
              or connectors you enable. Review our{" "}
              <Link
                href="/acceptable-use"
                className="text-blue-600 dark:text-blue-400 hover:underline underline-offset-2"
              >
                Acceptable Use Policy
              </Link>{" "}
              and{" "}
              <Link
                href="/privacy"
                className="text-blue-600 dark:text-blue-400 hover:underline underline-offset-2"
              >
                Privacy Policy
              </Link>{" "}
              for related commitments.
            </p>
            <div className="rounded-2xl border border-zinc-100 dark:border-card-border bg-background p-6">
              <h3 className="font-semibold text-foreground mb-2">
                Report a vulnerability
              </h3>
              <p className="text-sm mb-4">
                Email{" "}
                <a
                  href="mailto:security@cocomputer.com"
                  className="text-blue-600 dark:text-blue-400 hover:underline underline-offset-2"
                >
                  security@cocomputer.com
                </a>{" "}
                with a description, impact assessment, and steps to reproduce.
                Please give us a reasonable window to investigate before public
                disclosure.
              </p>
              <Link
                href="/contact"
                className="inline-flex px-5 py-2.5 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
              >
                Contact security
              </Link>
            </div>
          </div>
        </section>
      </main>
    </MarketingShell>
  );
}
