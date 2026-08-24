/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import type { ReactNode } from "react";
import { MarketingShell } from "@/components/marketing/marketing-shell";
import { MarketingHeroPanel } from "@/components/marketing/marketing-hero-panel";

export type LegalSection = {
  id?: string;
  title: string;
  content: ReactNode;
};

type LegalDocProps = {
  title: string;
  description?: string;
  lastUpdated: string;
  sections: LegalSection[];
};

export function LegalDoc({
  title,
  description,
  lastUpdated,
  sections,
}: LegalDocProps) {
  return (
    <MarketingShell>
      <main className="relative pt-28 pb-20 px-6">
        <div className="max-w-5xl mx-auto mb-14">
          <MarketingHeroPanel size="compact">
            <p className="text-[10px] font-bold uppercase tracking-widest text-blue-100/80 mb-4">
              Legal
            </p>
            <h1 className="font-serif text-3xl md:text-5xl text-white mb-4 leading-[1.15]">
              {title}
            </h1>
            {description ? (
              <p className="text-blue-100 text-base md:text-lg leading-relaxed max-w-2xl mx-auto text-balance mb-4">
                {description}
              </p>
            ) : null}
            <p className="text-sm text-blue-100/70">
              Last updated: {lastUpdated}
            </p>
          </MarketingHeroPanel>
        </div>

        <article className="relative z-10 max-w-3xl mx-auto">
          <div className="space-y-10">
            {sections.map((section, index) => (
              <section
                key={section.id ?? `${section.title}-${index}`}
                id={section.id}
                className="scroll-mt-28"
              >
                <h2 className="mb-3 font-serif text-xl tracking-tight text-foreground">
                  {section.title}
                </h2>
                <div className="space-y-3 text-sm md:text-[15px] text-muted-foreground leading-relaxed [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:space-y-2 [&_a]:text-blue-600 dark:[&_a]:text-blue-400 [&_a]:underline-offset-2 hover:[&_a]:underline [&_strong]:text-foreground [&_strong]:font-medium">
                  {section.content}
                </div>
              </section>
            ))}
          </div>

          <p className="mt-14 pt-8 border-t border-zinc-100 dark:border-card-border text-xs text-muted-foreground leading-relaxed">
            This page is a working draft for product use and is not a substitute
            for formal legal advice. Contact{" "}
            <a
              href="mailto:legal@cocomputer.com"
              className="text-blue-600 dark:text-blue-400 hover:underline underline-offset-2"
            >
              legal@cocomputer.com
            </a>{" "}
            with questions.
          </p>
        </article>
      </main>
    </MarketingShell>
  );
}
