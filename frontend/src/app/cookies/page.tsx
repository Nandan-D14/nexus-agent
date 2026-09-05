/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { LegalDoc } from "@/components/marketing/legal-doc";

export const metadata: Metadata = {
  title: "Cookie Policy — CoComputer",
  description:
    "How CoComputer uses cookies and similar technologies for authentication, preferences, and analytics.",
};

export default function CookiesPage() {
  return (
    <LegalDoc
      title="Cookie Policy"
      description="This Cookie Policy explains how CoComputer uses cookies and similar technologies when you visit our websites or use the Service."
      lastUpdated="August 4, 2026"
      sections={[
        {
          title: "1. What are cookies?",
          content: (
            <p>
              Cookies are small text files stored on your device. Similar
              technologies include local storage, session storage, and pixels.
              We use these to keep you signed in, remember preferences, and
              understand how the product is used.
            </p>
          ),
        },
        {
          title: "2. Types of cookies we use",
          content: (
            <>
              <ul>
                <li>
                  <strong>Essential</strong> — required for authentication,
                  security, load balancing, and core product functionality.
                  These cannot be disabled if you want to use the Service.
                </li>
                <li>
                  <strong>Preferences</strong> — remember settings such as theme
                  or UI choices.
                </li>
                <li>
                  <strong>Analytics</strong> — help us understand traffic,
                  feature usage, and performance (if enabled). Data is used in
                  aggregate where practical.
                </li>
              </ul>
              <p>
                We do not use cookies to sell personal information. For how we
                handle personal data more broadly, see our{" "}
                <Link href="/privacy">Privacy Policy</Link>.
              </p>
            </>
          ),
        },
        {
          title: "3. Third-party cookies",
          content: (
            <p>
              Sign-in and infrastructure providers (for example, Google/Firebase)
              may set their own cookies subject to their policies. If we add
              analytics or support tools, those vendors may also set cookies.
            </p>
          ),
        },
        {
          title: "4. Your choices",
          content: (
            <>
              <p>You can control cookies through:</p>
              <ul>
                <li>Your browser settings (block, delete, or alert on cookies)</li>
                <li>Signing out of your CoComputer account</li>
                <li>
                  Product preference controls, when available in Settings
                </li>
              </ul>
              <p>
                Blocking essential cookies may prevent login or break core
                features.
              </p>
            </>
          ),
        },
        {
          title: "5. Updates",
          content: (
            <p>
              We may update this Cookie Policy as our practices change. Check
              the “Last updated” date for the latest version.
            </p>
          ),
        },
        {
          title: "6. Contact",
          content: (
            <p>
              Questions:{" "}
              <a href="mailto:privacy@cocomputer.com">
                privacy@cocomputer.com
              </a>
              .
            </p>
          ),
        },
      ]}
    />
  );
}
