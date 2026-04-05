"use client";

import { authenticatedFetch, readApiError } from "./api-client";

export type BetaState = "none" | "pending_review" | "approved" | "rejected" | "revoked";

export type BetaApplicationSummary = {
  full_name: string;
  email: string;
  role: string;
  company_team: string;
  primary_use_case: string;
  current_workflow: string;
  why_access: string;
  expected_usage_frequency: string;
  acknowledge_byok: boolean;
  status: BetaState | string;
  sheet_sync_status?: string | null;
};

export type BetaStatusResponse = {
  state: BetaState;
  can_apply: boolean;
  can_access_app: boolean;
  needs_access_code: boolean;
  access_code_redeemed: boolean;
  requires_byok_setup: boolean;
  byok_missing: string[];
  message: string;
  application_submitted_at?: string | null;
  application_updated_at?: string | null;
  approved_at?: string | null;
  rejected_at?: string | null;
  revoked_at?: string | null;
  redeemed_at?: string | null;
  application?: BetaApplicationSummary | null;
};

export type BetaApplicationPayload = {
  full_name: string;
  role: string;
  company_team: string;
  primary_use_case: string;
  current_workflow: string;
  why_access: string;
  expected_usage_frequency: string;
  acknowledge_byok: boolean;
};

export async function fetchBetaStatus(): Promise<BetaStatusResponse> {
  const response = await authenticatedFetch("/api/v1/beta/status");
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
  return (await response.json()) as BetaStatusResponse;
}

export async function submitBetaApplication(
  payload: BetaApplicationPayload,
): Promise<BetaStatusResponse> {
  const response = await authenticatedFetch("/api/v1/beta/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
  return (await response.json()) as BetaStatusResponse;
}

export async function redeemBetaAccessCode(code: string): Promise<BetaStatusResponse> {
  const response = await authenticatedFetch("/api/v1/beta/redeem-code", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code }),
  });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
  return (await response.json()) as BetaStatusResponse;
}

export function isBetaBlockedCode(code: string | undefined): boolean {
  return Boolean(
    code &&
      [
        "BETA_APPLICATION_REQUIRED",
        "BETA_APPROVAL_PENDING",
        "BETA_ACCESS_CODE_REQUIRED",
        "BETA_ACCESS_REVOKED",
        "BETA_ACCESS_CODE_INVALID",
      ].includes(code),
  );
}
