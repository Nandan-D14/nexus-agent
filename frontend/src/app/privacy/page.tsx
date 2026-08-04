/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { LegalDoc } from "@/components/marketing/legal-doc";

export const metadata: Metadata = {
  title: "Privacy Policy — CoComputer",
  description:
    "How CoComputer collects, uses, and protects personal data for accounts, sessions, and product analytics.",
};

export default function PrivacyPage() {
  return (
    <LegalDoc
      title="Privacy Policy"
      description="This Privacy Policy explains how Agentic Company (“CoComputer,” “we,” “us”) collects, uses, and shares information when you use our Service."
      lastUpdated="August 4, 2026"
      sections={[
        {
          title: "1. Who we are",
          content: (
            <p>
              CoComputer is an AI desktop agent platform operated by Agentic
              Company. For privacy requests, contact{" "}
              <a href="mailto:privacy@cocomputer.com">
                privacy@cocomputer.com
              </a>
              .
            </p>
          ),
        },
        {
          title: "2. Information we collect",
          content: (
            <>
              <p>We may collect:</p>
              <ul>
                <li>
                  <strong>Account information</strong> — name, email, profile
                  photo, and identifiers from your sign-in provider (for
                  example, Google).
                </li>
                <li>
                  <strong>Usage and session metadata</strong> — session IDs,
                  timestamps, plan limits, feature usage, error logs, and
                  approximate device/browser information.
                </li>
                <li>
                  <strong>Content you provide</strong> — prompts, messages,
                  files you upload to a session or workspace, and connector
                  configuration you choose to enable.
                </li>
                <li>
                  <strong>Billing information</strong> — processed by our
                  payment providers; we typically receive limited billing
                  metadata (plan, status, invoices), not full card numbers.
                </li>
                <li>
                  <strong>Communications</strong> — messages you send to
                  support or sales.
                </li>
              </ul>
            </>
          ),
        },
        {
          title: "3. API keys and BYOK credentials",
          content: (
            <p>
              If you connect your own API keys, we process them only to route
              requests you initiate. Keys should be treated as secrets. We
              design the product so keys are not stored in plain text on our
              servers longer than needed for your session configuration; you
              remain responsible for rotating keys and reviewing third-party
              provider privacy terms.
            </p>
          ),
        },
        {
          title: "4. How we use information",
          content: (
            <>
              <p>We use information to:</p>
              <ul>
                <li>Provide, operate, and secure the Service</li>
                <li>Authenticate users and manage accounts</li>
                <li>Run sandboxes, tools, and model routing you request</li>
                <li>Bill for paid plans and prevent fraud or abuse</li>
                <li>Improve reliability, performance, and product quality</li>
                <li>Communicate about product updates and support</li>
                <li>Comply with law and enforce our Terms</li>
              </ul>
            </>
          ),
        },
        {
          title: "5. AI processing",
          content: (
            <p>
              Prompts and related context may be sent to model providers you
              select or that power default routing, so those providers can
              generate responses. Do not submit sensitive personal data unless
              necessary. Model providers process data under their own terms and
              privacy policies.
            </p>
          ),
        },
        {
          title: "6. Sharing and processors",
          content: (
            <>
              <p>
                We share information with service providers who help us run
                CoComputer, such as:
              </p>
              <ul>
                <li>Authentication and app data (for example, Firebase/Google)</li>
                <li>Cloud infrastructure and sandbox hosting</li>
                <li>Model and tool providers you use</li>
                <li>Payment processors for paid plans</li>
                <li>Analytics or error monitoring, if enabled</li>
              </ul>
              <p>
                We may also disclose information if required by law, to protect
                rights and safety, or in connection with a merger or
                acquisition.
              </p>
            </>
          ),
        },
        {
          title: "7. Retention",
          content: (
            <p>
              We retain account data while your account is active and for a
              reasonable period afterward for backups, dispute resolution, and
              legal compliance. Ephemeral sandbox files may be deleted when a
              session ends. Session history retention depends on your plan.
            </p>
          ),
        },
        {
          title: "8. Security",
          content: (
            <p>
              We use administrative, technical, and organizational measures
              designed to protect information, including encryption in transit
              and isolated sandboxes. No method of transmission or storage is
              fully secure. See our <Link href="/security">Security</Link> page
              for more detail.
            </p>
          ),
        },
        {
          title: "9. Your rights and choices",
          content: (
            <>
              <p>
                Depending on your location, you may have rights to access,
                correct, delete, or export personal data, or to object to or
                restrict certain processing. You can also sign out, disconnect
                integrations, and manage cookies as described in our{" "}
                <Link href="/cookies">Cookie Policy</Link>.
              </p>
              <p>
                To exercise privacy rights, email{" "}
                <a href="mailto:privacy@cocomputer.com">
                  privacy@cocomputer.com
                </a>
                . We may need to verify your request.
              </p>
            </>
          ),
        },
        {
          title: "10. International transfers",
          content: (
            <p>
              We may process information in the United States and other
              countries where we or our processors operate. Where required, we
              use appropriate transfer mechanisms.
            </p>
          ),
        },
        {
          title: "11. Children",
          content: (
            <p>
              The Service is not directed to children under 16 (or the minimum
              age in your jurisdiction). We do not knowingly collect personal
              information from children.
            </p>
          ),
        },
        {
          title: "12. Changes",
          content: (
            <p>
              We may update this Privacy Policy periodically. We will revise the
              “Last updated” date and, for material changes, provide additional
              notice when appropriate.
            </p>
          ),
        },
        {
          title: "13. Contact",
          content: (
            <p>
              Privacy inquiries:{" "}
              <a href="mailto:privacy@cocomputer.com">
                privacy@cocomputer.com
              </a>
              . General support:{" "}
              <a href="mailto:support@cocomputer.com">
                support@cocomputer.com
              </a>
              .
            </p>
          ),
        },
      ]}
    />
  );
}
