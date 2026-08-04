/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Github, Terminal } from "lucide-react";
import { BeamsBackground } from "@/components/react-bits/beams-background";

type SiteFooterProps = {
  showStatus?: boolean;
};

function FooterLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  const className =
    "hover:text-blue-500 transition-colors text-sm text-muted-foreground font-medium";
  if (href.startsWith("#") || href.startsWith("http")) {
    return (
      <a href={href} className={className}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}

export function SiteFooter({ showStatus = false }: SiteFooterProps) {
  return (
    <footer className="relative py-24 px-6 border-t border-zinc-100 dark:border-card-border bg-background overflow-hidden z-20">
      <BeamsBackground variant="footer" />

      <div className="relative z-10 max-w-7xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-12 gap-12 mb-16">
          <div className="col-span-2 md:col-span-4 space-y-6">
            <Link href="/" className="flex items-center gap-2 group">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-lg shadow-blue-500/20">
                <Terminal className="w-4 h-4" />
              </div>
              <span className="font-bold text-xl tracking-tighter text-foreground">
                CoComputer
              </span>
            </Link>
            <p className="text-muted-foreground text-sm leading-relaxed max-w-xs">
              Autonomous multimodal neural architecture bridging the gap between
              human language and native Linux environments.
            </p>
            <div className="flex items-center gap-4">
              <a
                href="https://x.com"
                className="text-muted-foreground hover:text-blue-500 transition-colors"
                aria-label="X"
              >
                <svg
                  className="w-5 h-5"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </a>
              <a
                href="https://github.com"
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label="GitHub"
              >
                <Github className="w-5 h-5" />
              </a>
            </div>
          </div>

          <div className="col-span-1 md:col-span-2 space-y-4">
            <h5 className="text-xs font-bold uppercase tracking-widest text-foreground">
              Product
            </h5>
            <ul className="space-y-3">
              <li>
                <FooterLink href="/#features">Features</FooterLink>
              </li>
              <li>
                <FooterLink href="/pricing">Pricing</FooterLink>
              </li>
            </ul>
          </div>

          <div className="col-span-1 md:col-span-2 space-y-4">
            <h5 className="text-xs font-bold uppercase tracking-widest text-foreground">
              Company
            </h5>
            <ul className="space-y-3">
              <li>
                <FooterLink href="/about">About</FooterLink>
              </li>
              <li>
                <FooterLink href="/contact">Contact</FooterLink>
              </li>
              <li>
                <FooterLink href="/security">Security</FooterLink>
              </li>
            </ul>
          </div>

          <div className="col-span-2 md:col-span-4 space-y-4">
            <h5 className="text-xs font-bold uppercase tracking-widest text-foreground">
              Legal
            </h5>
            <ul className="space-y-3">
              <li>
                <FooterLink href="/terms">Terms of Service</FooterLink>
              </li>
              <li>
                <FooterLink href="/privacy">Privacy Policy</FooterLink>
              </li>
              <li>
                <FooterLink href="/cookies">Cookie Policy</FooterLink>
              </li>
              <li>
                <FooterLink href="/acceptable-use">Acceptable Use</FooterLink>
              </li>
              <li>
                <FooterLink href="/refund">Refund Policy</FooterLink>
              </li>
            </ul>
          </div>
        </div>

        <div className="pt-8 border-t border-zinc-100 dark:border-zinc-800/50 flex flex-col md:flex-row justify-between items-center gap-6 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
          <p>
            &copy; {new Date().getFullYear()} CoComputer Systems. All rights
            reserved.
          </p>
          <div className="flex items-center gap-6">
            <Link
              href="/privacy"
              className="hover:text-zinc-900 dark:hover:text-white transition-colors"
            >
              Privacy Policy
            </Link>
            <Link
              href="/terms"
              className="hover:text-zinc-900 dark:hover:text-white transition-colors"
            >
              Terms of Service
            </Link>
            {showStatus ? (
              <div className="flex items-center gap-2 text-emerald-500">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                SYSTEMS OPERATIONAL
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </footer>
  );
}
