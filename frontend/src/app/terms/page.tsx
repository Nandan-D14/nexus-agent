/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { LegalDoc } from "@/components/marketing/legal-doc";

export const metadata: Metadata = {
  title: "Terms of Service — CoComputer",
  description:
    "Terms governing your use of CoComputer, including accounts, sandboxes, billing, and acceptable use.",
};

export default function TermsPage() {
  return (
    <LegalDoc
      title="Terms of Service"
      description="These Terms of Service govern access to and use of CoComputer, operated by nandan-d14 (“CoComputer,” “we,” “us,” or “our”)."
      lastUpdated="August 4, 2026"
      sections={[
        {
          title: "1. Acceptance of terms",
          content: (
            <>
              <p>
                By creating an account, accessing the Service, or launching a
                session, you agree to these Terms and our{" "}
                <Link href="/privacy">Privacy Policy</Link>,{" "}
                <Link href="/cookies">Cookie Policy</Link>, and{" "}
                <Link href="/acceptable-use">Acceptable Use Policy</Link>. If
                you do not agree, do not use the Service.
              </p>
              <p>
                If you use CoComputer on behalf of an organization, you represent
                that you have authority to bind that organization to these
                Terms.
              </p>
            </>
          ),
        },
        {
          title: "2. The Service",
          content: (
            <>
              <p>
                CoComputer provides an AI-assisted cloud desktop agent,
                including conversational interfaces, isolated Linux sandboxes,
                tools (such as terminal, browser, and web search), session
                history, and related features. Features may vary by plan and may
                change as we improve the product.
              </p>
              <p>
                The Service is provided for lawful business and personal
                productivity use. Beta or experimental features may be less
                reliable and may be modified or withdrawn at any time.
              </p>
            </>
          ),
        },
        {
          title: "3. Accounts and authentication",
          content: (
            <>
              <p>
                You must sign in with a supported identity provider (for
                example, Google) and provide accurate account information. You
                are responsible for maintaining the security of your account and
                for all activity under it.
              </p>
              <p>
                Notify us promptly at{" "}
                <a href="mailto:support@cocomputer.com">
                  support@cocomputer.com
                </a>{" "}
                if you suspect unauthorized access.
              </p>
            </>
          ),
        },
        {
          title: "4. Sandboxes and sessions",
          content: (
            <>
              <p>
                Each session may boot an isolated cloud environment with Linux
                access, tools, and temporary storage. Unless a feature
                explicitly persists data to your workspace or connectors, files
                and processes may be deleted when a session ends or expires.
              </p>
              <p>
                You are responsible for exporting or saving work you need to
                keep. Do not rely on ephemeral sandboxes as long-term storage.
                Resource limits (session duration, compute, network) apply
                according to your plan.
              </p>
            </>
          ),
        },
        {
          title: "5. API keys and third-party services (BYOK)",
          content: (
            <>
              <p>
                Where CoComputer supports Bring Your Own Key (BYOK), you may
                supply API keys or credentials for model providers and
                integrations. You are responsible for those credentials, their
                billing with third parties, and compliance with third-party
                terms.
              </p>
              <p>
                We do not claim ownership of your keys. Handle keys carefully;
                revoke and rotate them if you believe they were exposed.
              </p>
            </>
          ),
        },
        {
          title: "6. Acceptable use",
          content: (
            <p>
              You must comply with our{" "}
              <Link href="/acceptable-use">Acceptable Use Policy</Link>. We may
              suspend or terminate access for violations, abuse of sandboxes, or
              activity that harms the Service or other users.
            </p>
          ),
        },
        {
          title: "7. Plans, billing, and cancellations",
          content: (
            <>
              <p>
                Free, Pro, and Enterprise plans may include different limits and
                features. Paid plans are billed according to the pricing shown
                at checkout or in an order form. Taxes may apply.
              </p>
              <p>
                You may cancel or change plans as described on our{" "}
                <Link href="/pricing">Pricing</Link> page and{" "}
                <Link href="/refund">Refund &amp; Cancellation Policy</Link>.
                Failure to pay may result in suspension or downgrade.
              </p>
            </>
          ),
        },
        {
          title: "8. Your content and intellectual property",
          content: (
            <>
              <p>
                You retain ownership of content you submit or create in the
                Service (“Your Content”), subject to rights you grant third-party
                providers when you use their APIs. You grant CoComputer a
                limited license to host, process, and display Your Content solely
                to provide and improve the Service.
              </p>
              <p>
                CoComputer and its licensors own the Service, software, branding,
                and documentation. These Terms do not grant you rights to our
                trademarks or source code except as expressly permitted.
              </p>
            </>
          ),
        },
        {
          title: "9. AI outputs and disclaimers",
          content: (
            <>
              <p>
                AI-generated outputs may be inaccurate, incomplete, or
                inappropriate. You are responsible for reviewing outputs before
                relying on them, especially for production systems, legal,
                financial, or safety-critical decisions.
              </p>
              <p>
                THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE,” WITHOUT
                WARRANTIES OF ANY KIND, WHETHER EXPRESS OR IMPLIED, INCLUDING
                MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
                NON-INFRINGEMENT, TO THE MAXIMUM EXTENT PERMITTED BY LAW.
              </p>
            </>
          ),
        },
        {
          title: "10. Limitation of liability",
          content: (
            <p>
              To the maximum extent permitted by law, CoComputer and its
              affiliates will not be liable for indirect, incidental, special,
              consequential, or punitive damages, or for loss of profits, data,
              goodwill, or business interruption. Our aggregate liability arising
              out of these Terms or the Service will not exceed the greater of
              (a) amounts you paid us for the Service in the twelve (12) months
              before the claim or (b) one hundred U.S. dollars (US $100) if you
              use only a free plan.
            </p>
          ),
        },
        {
          title: "11. Termination",
          content: (
            <p>
              You may stop using the Service at any time. We may suspend or
              terminate access if you violate these Terms, if required by law, or
              if we discontinue the Service. Upon termination, your right to use
              the Service ends, and ephemeral session data may be deleted
              according to our retention practices.
            </p>
          ),
        },
        {
          title: "12. Changes",
          content: (
            <p>
              We may update these Terms from time to time. Material changes will
              be indicated by updating the “Last updated” date and, where
              appropriate, by notice in the product or by email. Continued use
              after changes become effective constitutes acceptance.
            </p>
          ),
        },
        {
          title: "13. Contact",
          content: (
            <p>
              Questions about these Terms:{" "}
              <a href="mailto:legal@cocomputer.com">legal@cocomputer.com</a>.
              General support:{" "}
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
