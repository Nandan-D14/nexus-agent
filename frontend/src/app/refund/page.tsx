/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { LegalDoc } from "@/components/marketing/legal-doc";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy — CoComputer",
  description:
    "How cancellations, plan changes, and refunds work for CoComputer Free, Pro, and Enterprise plans.",
};

export default function RefundPage() {
  return (
    <LegalDoc
      title="Refund & Cancellation Policy"
      description="This policy explains how plan changes, cancellations, and refunds work for CoComputer subscriptions."
      lastUpdated="August 4, 2026"
      sections={[
        {
          title: "1. Free plan",
          content: (
            <p>
              The Free plan has no subscription fee. Session and feature limits
              apply as described on our <Link href="/pricing">Pricing</Link>{" "}
              page. There is nothing to refund on Free.
            </p>
          ),
        },
        {
          title: "2. Cancelling Pro",
          content: (
            <>
              <p>
                You may cancel a Pro subscription at any time from account
                billing settings (or by contacting support if self-serve cancel
                is unavailable). Cancellation stops future renewals.
              </p>
              <p>
                You generally retain Pro access until the end of the current
                paid billing period. Downgrades take effect at the end of that
                period unless we state otherwise at checkout.
              </p>
            </>
          ),
        },
        {
          title: "3. Refunds",
          content: (
            <>
              <p>
                Except where required by law, paid subscription fees are
                non-refundable once a billing period has started. We may, at our
                sole discretion, issue a prorated credit or refund when:
              </p>
              <ul>
                <li>
                  You were charged due to a clear billing error on our side
                </li>
                <li>
                  A sustained Service outage materially prevented use and we
                  determine a credit is appropriate
                </li>
                <li>
                  A promotional trial or order form expressly promises a refund
                  window
                </li>
              </ul>
              <p>
                Refund requests should be sent to{" "}
                <a href="mailto:billing@cocomputer.com">
                  billing@cocomputer.com
                </a>{" "}
                within thirty (30) days of the charge, with your account email
                and invoice details.
              </p>
            </>
          ),
        },
        {
          title: "4. Upgrades and plan changes",
          content: (
            <p>
              Upgrades may take effect immediately, with charges adjusted for
              the remaining period as shown at checkout. Switching from monthly
              to annual (or the reverse) follows the billing terms presented
              when you confirm the change.
            </p>
          ),
        },
        {
          title: "5. Enterprise",
          content: (
            <p>
              Enterprise agreements are governed by the applicable order form or
              master services agreement. Cancellation, credits, and refunds for
              Enterprise follow that contract, not this consumer-facing policy.
              Contact{" "}
              <a href="mailto:sales@cocomputer.com">sales@cocomputer.com</a>{" "}
              for Enterprise billing questions.
            </p>
          ),
        },
        {
          title: "6. Chargebacks",
          content: (
            <p>
              Please contact us before initiating a chargeback so we can help
              resolve the issue. Fraudulent or abusive chargebacks may result in
              account suspension.
            </p>
          ),
        },
        {
          title: "7. Contact",
          content: (
            <p>
              Billing support:{" "}
              <a href="mailto:billing@cocomputer.com">
                billing@cocomputer.com
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
