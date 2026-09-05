/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import { MarketingShell } from "@/components/marketing/marketing-shell";
import { MarketingHeroPanel } from "@/components/marketing/marketing-hero-panel";
import { ContactForm } from "@/components/marketing/contact-form";

export const metadata: Metadata = {
  title: "Contact — CoComputer",
  description:
    "Contact CoComputer support, sales, or security. Send a message and we will get back to you.",
};

export default function ContactPage() {
  return (
    <MarketingShell>
      <main>
        <section className="relative pt-28 pb-8 px-6">
          <div className="max-w-5xl mx-auto">
            <MarketingHeroPanel size="compact">
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-100/80 mb-4">
                Contact
              </p>
              <h1 className="font-serif text-3xl md:text-5xl text-white mb-4 leading-[1.15]">
                Get in touch
              </h1>
              <p className="text-blue-100 text-lg max-w-xl mx-auto text-balance">
                Reach support, sales, or security. The form below opens your
                email client with a pre-filled message — no account required.
              </p>
            </MarketingHeroPanel>
          </div>
        </section>

        <section className="py-8 px-6 pb-20">
          <ContactForm />
        </section>
      </main>
    </MarketingShell>
  );
}
