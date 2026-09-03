/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { BeamsBackground } from "@/components/react-bits/beams-background";
import { CocomputerLogo } from "@/components/brand/cocomputer-logo";

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
              <CocomputerLogo size={32} wordmarkClassName="text-xl tracking-tighter font-bold" />
            </Link>
            <p className="text-muted-foreground text-sm leading-relaxed max-w-xs">
              A cloud Linux desktop your agent can see and use — chat, terminal,
              browser, and the connectors you connect.
            </p>
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
                <FooterLink href="/#integrations">Integrations</FooterLink>
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
