/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { KeyRound, Plug, RotateCcw, ShieldCheck } from "lucide-react";

import { ConnectorLogo } from "@/components/connectors/connector-logo";
import { useSignInGate } from "@/components/auth/sign-in-gate";
import { useAuth } from "@/lib/auth-context";

type Connector = {
  /** Must match a key handled by `providerLogo` in `@/lib/connectors`. */
  provider: string;
  name: string;
  /** What the agent can do once you authorize it. */
  capability: string;
};

type ConnectorGroup = {
  label: string;
  blurb: string;
  items: Connector[];
};

/**
 * Capability lines are derived from CONNECTOR_DETAILS in `@/lib/connectors`
 * so marketing claims stay in step with what the agent can actually call.
 */
const GROUPS: ConnectorGroup[] = [
  {
    label: "Files, mail & calendar",
    blurb: "One Google sign-in covers all four.",
    items: [
      {
        provider: "google_drive",
        name: "Google Drive",
        capability: "Search, read, create, and upload files.",
      },
      {
        provider: "gmail",
        name: "Gmail",
        capability: "Triage threads, draft replies, send on your behalf.",
      },
      {
        provider: "google_calendar",
        name: "Google Calendar",
        capability: "List upcoming events and schedule new ones.",
      },
      {
        provider: "google_tasks",
        name: "Google Tasks",
        capability: "Add to-dos with due dates and check them off.",
      },
    ],
  },
  {
    label: "Code & deploy",
    blurb: "Ship without leaving the session.",
    items: [
      {
        provider: "github",
        name: "GitHub",
        capability: "Search, clone, create repos, push, issues, and PRs.",
      },
      {
        provider: "vercel",
        name: "Vercel",
        capability: "Inspect projects, deployments, and build logs.",
      },
      {
        provider: "cloudflare",
        name: "Cloudflare",
        capability: "Manage Workers, DNS, and account resources.",
      },
    ],
  },
  {
    label: "Planning & comms",
    blurb: "Keep the rest of the team in the loop.",
    items: [
      {
        provider: "linear",
        name: "Linear",
        capability: "Search and update issues, projects, and comments.",
      },
      {
        provider: "slack",
        name: "Slack",
        capability: "Read channel history and post updates.",
      },
    ],
  },
  {
    label: "Research & the live web",
    blurb: "Reach past the sandbox for current, citable information.",
    items: [
      {
        provider: "exa",
        name: "Exa",
        capability: "Semantic search plus clean full-page fetch.",
      },
      {
        provider: "tavily",
        name: "Tavily",
        capability: "Agent-shaped web search with concise sources.",
      },
      {
        provider: "openai",
        name: "OpenAI",
        capability: "Web search through the Responses API.",
      },
      {
        provider: "treg",
        name: "Treg",
        capability: "SEO, SERP, backlink, and enrichment APIs.",
      },
    ],
  },
  {
    label: "Automation & anything else",
    blurb: "Not on the list? Bring your own.",
    items: [
      {
        provider: "apify",
        name: "Apify",
        capability: "Run scrapers and read datasets.",
      },
      {
        provider: "tinyfish",
        name: "Tinyfish",
        capability: "Drive real websites from a plain-language goal.",
      },
      {
        provider: "composio",
        name: "Composio",
        capability: "1000+ app actions behind one connection.",
      },
      {
        provider: "mcp",
        name: "Custom MCP",
        capability: "Point the agent at any MCP server you run.",
      },
    ],
  },
];

const GUARANTEES = [
  {
    icon: Plug,
    text: "Nothing is connected by default. You authorize each one.",
  },
  {
    icon: ShieldCheck,
    text: "The agent can only reach what you have turned on.",
  },
  {
    icon: RotateCcw,
    text: "Revoke any connector from Settings at any time.",
  },
];

export function IntegrationsSection({
  connectorsHref,
}: {
  connectorsHref: string;
}) {
  const { user } = useAuth();
  const { requestSignIn } = useSignInGate();

  /** The connector catalog lives behind auth — gate it instead of bouncing off a login wall. */
  const handleBrowse = (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (user) return;
    event.preventDefault();
    requestSignIn({
      reason:
        "The connector catalog is part of your workspace. Sign in with Google to browse and authorize integrations.",
      redirectTo: connectorsHref,
    });
  };

  return (
    <section
      id="integrations"
      className="relative overflow-hidden border-t border-zinc-100 py-28 dark:border-card-border"
    >
      <div className="mx-auto max-w-6xl px-6">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-blue-600 dark:text-blue-500">
            Integrations
          </p>
          <h2 className="mb-5 font-serif text-3xl leading-tight tracking-tight text-foreground md:text-5xl">
            Connect the tools you already use
          </h2>
          <p className="text-lg leading-relaxed text-muted-foreground">
            On its own the desktop can browse and run code. Connect an account
            and the agent can act in the systems your work actually lives in.
          </p>
        </div>

        <div className="space-y-12">
          {GROUPS.map((group, groupIndex) => (
            <motion.div
              key={group.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{
                duration: 0.6,
                delay: Math.min(groupIndex * 0.06, 0.24),
                ease: [0.22, 1, 0.36, 1],
              }}
            >
              <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h3 className="text-sm font-semibold tracking-tight text-foreground">
                  {group.label}
                </h3>
                <p className="text-sm text-muted-foreground">{group.blurb}</p>
              </div>

              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {group.items.map((item) => (
                  <li key={item.provider}>
                    <div className="flex h-full items-start gap-4 rounded-2xl border border-zinc-200/80 bg-white p-5 transition-colors hover:border-blue-300 dark:border-white/10 dark:bg-zinc-950 dark:hover:border-blue-500/40">
                      <ConnectorLogo
                        provider={item.provider}
                        name={item.name}
                        size="sm"
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold tracking-tight text-foreground">
                          {item.name}
                        </p>
                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                          {item.capability}
                        </p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>

        <div className="mt-14 rounded-2xl border border-zinc-200/80 bg-zinc-50/60 p-6 dark:border-white/10 dark:bg-white/[0.02]">
          <ul className="grid gap-4 sm:grid-cols-3">
            {GUARANTEES.map((guarantee) => (
              <li key={guarantee.text} className="flex items-start gap-3">
                <guarantee.icon
                  className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
                  aria-hidden
                />
                <span className="text-sm leading-relaxed text-muted-foreground">
                  {guarantee.text}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-10 flex flex-col items-center justify-center gap-x-6 gap-y-3 sm:flex-row">
          <Link
            href={connectorsHref}
            onClick={handleBrowse}
            className="text-sm font-medium text-blue-600 underline-offset-4 hover:underline dark:text-blue-400"
          >
            Browse all connectors
          </Link>
          <span
            aria-hidden
            className="hidden h-4 w-px bg-zinc-200 sm:block dark:bg-white/10"
          />
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <KeyRound className="size-3.5 shrink-0" aria-hidden />
            Models are separate — bring your own provider keys.
          </p>
        </div>
      </div>
    </section>
  );
}
