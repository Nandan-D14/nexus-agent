/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { LegalDoc } from "@/components/marketing/legal-doc";

export const metadata: Metadata = {
  title: "Acceptable Use Policy — CoComputer",
  description:
    "Rules for using CoComputer sandboxes, agents, and tools safely and lawfully.",
};

export default function AcceptableUsePage() {
  return (
    <LegalDoc
      title="Acceptable Use Policy"
      description="This Acceptable Use Policy (“AUP”) describes prohibited and required conduct when using CoComputer. It forms part of our Terms of Service."
      lastUpdated="August 4, 2026"
      sections={[
        {
          title: "1. Purpose",
          content: (
            <p>
              CoComputer gives users powerful access to cloud desktops, agents,
              and automation tools. This AUP protects users, infrastructure, and
              the public internet from abuse. Violations may result in
              suspension or termination under our{" "}
              <Link href="/terms">Terms of Service</Link>.
            </p>
          ),
        },
        {
          title: "2. Prohibited activities",
          content: (
            <>
              <p>You may not use the Service to:</p>
              <ul>
                <li>
                  Violate any law or regulation, or infringe intellectual
                  property, privacy, or other rights
                </li>
                <li>
                  Create, distribute, or operate malware, ransomware, spyware,
                  botnets, or other harmful code
                </li>
                <li>
                  Attempt unauthorized access to systems, networks, accounts, or
                  data (including scanning or exploiting vulnerabilities without
                  explicit authorization)
                </li>
                <li>
                  Launch denial-of-service attacks, spam campaigns, or abusive
                  bulk messaging
                </li>
                <li>
                  Mine cryptocurrency or run similarly intensive workloads that
                  evade plan limits
                </li>
                <li>
                  Abuse sandboxes to host public services, open relays, or
                  persistent attack infrastructure
                </li>
                <li>
                  Scrape or harvest personal data at scale without a lawful
                  basis and compliance with applicable rules
                </li>
                <li>
                  Generate or distribute child sexual abuse material, or content
                  that facilitates violent crime or terrorism
                </li>
                <li>
                  Harass, stalk, or threaten individuals, or engage in doxxing
                </li>
                <li>
                  Circumvent rate limits, billing, authentication, or safety
                  controls
                </li>
                <li>
                  Resell or share account access in a way that violates your
                  plan or these rules
                </li>
              </ul>
            </>
          ),
        },
        {
          title: "3. Sandbox and resource responsibility",
          content: (
            <p>
              You are responsible for software you install and commands you run
              inside sessions. Keep workloads within plan limits. Do not attempt
              to escape isolation boundaries, probe host infrastructure, or
              interfere with other customers’ environments.
            </p>
          ),
        },
        {
          title: "4. Credentials and secrets",
          content: (
            <p>
              Do not use CoComputer to steal, phish for, or misuse credentials.
              Protect API keys you bring into the product. Rotate keys if they
              may have been exposed in logs, chat, or shared sessions.
            </p>
          ),
        },
        {
          title: "5. Reporting abuse",
          content: (
            <p>
              Report suspected abuse or AUP violations to{" "}
              <a href="mailto:abuse@cocomputer.com">abuse@cocomputer.com</a>.
              Include relevant session IDs, timestamps, and evidence when
              possible.
            </p>
          ),
        },
        {
          title: "6. Enforcement",
          content: (
            <p>
              We may investigate suspected violations, remove content, throttle
              usage, suspend accounts, or involve law enforcement when
              appropriate. We may update this AUP as threats and product
              capabilities evolve.
            </p>
          ),
        },
      ]}
    />
  );
}
