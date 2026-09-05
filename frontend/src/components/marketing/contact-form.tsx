/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, type FormEvent } from "react";
import { Mail, MessageSquare, Building2 } from "lucide-react";

const channels = [
  {
    icon: Mail,
    title: "Support",
    detail: "support@cocomputer.com",
    href: "mailto:support@cocomputer.com",
    description: "Product help, account issues, and technical questions.",
  },
  {
    icon: Building2,
    title: "Sales",
    detail: "sales@cocomputer.com",
    href: "mailto:sales@cocomputer.com",
    description: "Enterprise plans, custom sandboxes, and team rollout.",
  },
  {
    icon: MessageSquare,
    title: "Security",
    detail: "security@cocomputer.com",
    href: "mailto:security@cocomputer.com",
    description: "Vulnerability reports and security inquiries.",
  },
];

export function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [topic, setTopic] = useState("support");
  const [message, setMessage] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const to =
      topic === "sales"
        ? "sales@cocomputer.com"
        : topic === "security"
          ? "security@cocomputer.com"
          : topic === "billing"
            ? "billing@cocomputer.com"
            : "support@cocomputer.com";
    const subject = encodeURIComponent(
      `[CoComputer ${topic}] Message from ${name || "website"}`,
    );
    const body = encodeURIComponent(
      `Name: ${name}\nEmail: ${email}\nTopic: ${topic}\n\n${message}`,
    );
    window.location.href = `mailto:${to}?subject=${subject}&body=${body}`;
  };

  return (
    <>
      <div className="max-w-6xl mx-auto grid md:grid-cols-3 gap-4 mb-12">
        {channels.map((channel) => (
          <a
            key={channel.title}
            href={channel.href}
            className="rounded-2xl border border-zinc-100 dark:border-card-border bg-zinc-50/50 dark:bg-zinc-900/30 p-6 hover:border-blue-300 dark:hover:border-blue-800 transition-colors"
          >
            <channel.icon className="w-5 h-5 text-blue-600 dark:text-blue-400 mb-3" />
            <h2 className="font-semibold text-foreground mb-1">
              {channel.title}
            </h2>
            <p className="text-sm text-blue-600 dark:text-blue-400 mb-2">
              {channel.detail}
            </p>
            <p className="text-sm text-muted-foreground">
              {channel.description}
            </p>
          </a>
        ))}
      </div>

      <div className="max-w-2xl mx-auto rounded-2xl border border-zinc-100 dark:border-card-border bg-background p-6 md:p-8">
        <h2 className="text-xl font-semibold tracking-tight text-foreground mb-6">
          Send a message
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <label className="block space-y-1.5">
              <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                Name
              </span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                placeholder="Your name"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                Email
              </span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                placeholder="you@company.com"
              />
            </label>
          </div>

          <label className="block space-y-1.5">
            <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
              Topic
            </span>
            <select
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="w-full bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              <option value="support">Support</option>
              <option value="sales">Sales / Enterprise</option>
              <option value="security">Security</option>
              <option value="billing">Billing</option>
            </select>
          </label>

          <label className="block space-y-1.5">
            <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
              Message
            </span>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              required
              rows={6}
              className="w-full bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 resize-y"
              placeholder="How can we help?"
            />
          </label>

          <button
            type="submit"
            className="w-full sm:w-auto px-6 py-2.5 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
          >
            Open email draft
          </button>
          <p className="text-xs text-muted-foreground">
            This opens your default mail app. We do not store form submissions
            on our servers from this page.
          </p>
        </form>
      </div>
    </>
  );
}
