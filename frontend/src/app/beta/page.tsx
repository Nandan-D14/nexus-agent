"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, Clock3, KeyRound, Loader2, LockKeyhole, ShieldAlert } from "lucide-react";

import { useToast } from "@/components/toast-provider";
import { useAuth } from "@/lib/auth-context";
import {
  fetchBetaStatus,
  redeemBetaAccessCode,
  submitBetaApplication,
  type BetaApplicationPayload,
  type BetaStatusResponse,
} from "@/lib/beta-access";

const EMPTY_FORM: BetaApplicationPayload = {
  full_name: "",
  role: "",
  company_team: "",
  primary_use_case: "",
  current_workflow: "",
  why_access: "",
  expected_usage_frequency: "",
  acknowledge_byok: true,
};

function buildInitialForm(status: BetaStatusResponse | null, fallbackName: string | null): BetaApplicationPayload {
  const application = status?.application;
  return {
    full_name: application?.full_name || fallbackName || "",
    role: application?.role || "",
    company_team: application?.company_team || "",
    primary_use_case: application?.primary_use_case || "",
    current_workflow: application?.current_workflow || "",
    why_access: application?.why_access || "",
    expected_usage_frequency: application?.expected_usage_frequency || "",
    acknowledge_byok: application?.acknowledge_byok ?? true,
  };
}

export default function BetaAccessPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { user, isLoading: authLoading, signInWithGoogle } = useAuth();

  const [status, setStatus] = useState<BetaStatusResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRedeeming, setIsRedeeming] = useState(false);
  const [accessCode, setAccessCode] = useState("");
  const [form, setForm] = useState<BetaApplicationPayload>(EMPTY_FORM);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!user) {
        if (!cancelled) {
          setStatus(null);
          setLoadError(null);
          setIsLoadingStatus(false);
          setForm(EMPTY_FORM);
        }
        return;
      }

      try {
        const nextStatus = await fetchBetaStatus();
        if (cancelled) {
          return;
        }
        setStatus(nextStatus);
        setLoadError(null);
        setForm(buildInitialForm(nextStatus, user.displayName));
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load beta access.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingStatus(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [user]);

  const statusBadge = useMemo(() => {
    if (!status) {
      return "Early Access";
    }
    if (status.can_access_app) {
      return "Beta Unlocked";
    }
    if (status.needs_access_code) {
      return "Approved";
    }
    if (status.state === "pending_review") {
      return "Pending Review";
    }
    if (status.state === "rejected") {
      return "Needs Update";
    }
    if (status.state === "revoked") {
      return "Access Revoked";
    }
    return "Apply for Access";
  }, [status]);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      const nextStatus = await submitBetaApplication(form);
      setStatus(nextStatus);
      setForm(buildInitialForm(nextStatus, user?.displayName ?? null));
      toast("Beta application submitted.", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to submit beta application.", "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRedeem = async () => {
    setIsRedeeming(true);
    try {
      const nextStatus = await redeemBetaAccessCode(accessCode.trim());
      setStatus(nextStatus);
      setAccessCode("");
      toast("Beta access code accepted.", "success");
      if (nextStatus.requires_byok_setup) {
        router.push("/settings/api?setup=1");
        return;
      }
      if (nextStatus.can_access_app) {
        router.push("/dashboard");
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to redeem access code.", "error");
    } finally {
      setIsRedeeming(false);
    }
  };

  if (authLoading || isLoadingStatus) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-100">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 px-6 text-zinc-100">
        <div className="w-full max-w-lg rounded-[2rem] border border-white/10 bg-white/5 p-8 text-center shadow-2xl backdrop-blur">
          <p className="text-xs font-semibold uppercase tracking-[0.25em] text-cyan-300">Controlled Beta</p>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">Sign in to request access</h1>
          <p className="mt-3 text-sm text-zinc-400">
            This beta is limited to approved users. Sign in with Google to submit your use case and receive an access code after review.
          </p>
          <button
            type="button"
            onClick={() => { void signInWithGoogle().catch(() => {}); }}
            className="mt-8 inline-flex w-full items-center justify-center rounded-full bg-cyan-500 px-5 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-cyan-400"
          >
            Sign in with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 px-6 py-12 text-zinc-100">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 lg:flex-row">
        <section className="flex-1 rounded-[2rem] border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-cyan-300">
            <LockKeyhole className="h-3.5 w-3.5" />
            {statusBadge}
          </div>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight">CoComputer internal beta access</h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-zinc-400">
            Register first, get approved manually, redeem your beta access code, then finish API and keys setup before running sessions. Firestore is the source of truth and your beta intake is mirrored into Google Sheets for review.
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
              <Clock3 className="h-5 w-5 text-cyan-300" />
              <p className="mt-3 text-sm font-medium">Manual review</p>
              <p className="mt-1 text-xs leading-5 text-zinc-500">Each beta application is reviewed before access is approved.</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
              <KeyRound className="h-5 w-5 text-cyan-300" />
              <p className="mt-3 text-sm font-medium">Access code redemption</p>
              <p className="mt-1 text-xs leading-5 text-zinc-500">Approved users unlock the product with a single-user beta access code.</p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
              <ShieldAlert className="h-5 w-5 text-cyan-300" />
              <p className="mt-3 text-sm font-medium">BYOK after approval</p>
              <p className="mt-1 text-xs leading-5 text-zinc-500">You will complete API and keys setup after approval and code redemption.</p>
            </div>
          </div>
        </section>

        <section className="w-full rounded-[2rem] border border-white/10 bg-[#101114] p-8 shadow-2xl lg:max-w-xl">
          {loadError ? (
            <div className="rounded-3xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {loadError}
            </div>
          ) : null}

          {!status || status.can_apply ? (
            <div className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">Apply for beta access</h2>
                <p className="mt-2 text-sm text-zinc-400">
                  Use your real workflow details. These answers are reviewed manually before an access code is issued.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-300">
                Signed in as <span className="font-medium text-white">{user.email}</span>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Full Name</span>
                  <input value={form.full_name} onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Role</span>
                  <input value={form.role} onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value }))} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
                </label>
              </div>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Company or Team</span>
                <input value={form.company_team} onChange={(event) => setForm((prev) => ({ ...prev, company_team: event.target.value }))} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Primary Use Case</span>
                <textarea value={form.primary_use_case} onChange={(event) => setForm((prev) => ({ ...prev, primary_use_case: event.target.value }))} rows={3} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">What do you do today?</span>
                <textarea value={form.current_workflow} onChange={(event) => setForm((prev) => ({ ...prev, current_workflow: event.target.value }))} rows={4} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Why do you want access?</span>
                <textarea value={form.why_access} onChange={(event) => setForm((prev) => ({ ...prev, why_access: event.target.value }))} rows={4} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Expected Usage Frequency</span>
                <input value={form.expected_usage_frequency} onChange={(event) => setForm((prev) => ({ ...prev, expected_usage_frequency: event.target.value }))} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm outline-none transition focus:border-cyan-400" />
              </label>

              <label className="flex items-start gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-300">
                <input type="checkbox" checked={form.acknowledge_byok} onChange={(event) => setForm((prev) => ({ ...prev, acknowledge_byok: event.target.checked }))} className="mt-1" />
                <span>I understand that this beta requires API and keys setup after approval and access-code redemption.</span>
              </label>

              <button type="button" onClick={() => void handleSubmit()} disabled={isSubmitting} className="inline-flex w-full items-center justify-center rounded-full bg-cyan-500 px-5 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60">
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit Beta Application"}
              </button>
            </div>
          ) : status.state === "pending_review" ? (
            <div className="space-y-5">
              <h2 className="text-xl font-semibold tracking-tight">Application received</h2>
              <p className="text-sm text-zinc-400">{status.message}</p>
              <div className="rounded-3xl border border-amber-400/20 bg-amber-400/10 px-5 py-4 text-sm text-amber-100">
                We are reviewing your use case. Once approved, you will receive a beta access code for this account.
              </div>
            </div>
          ) : status.needs_access_code ? (
            <div className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">Redeem your beta access code</h2>
                <p className="mt-2 text-sm text-zinc-400">
                  Your beta request is approved. Enter the code assigned to this account. You will complete API and keys setup immediately after redemption.
                </p>
              </div>
              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Beta Access Code</span>
                <input value={accessCode} onChange={(event) => setAccessCode(event.target.value)} placeholder="NEX-XXXX-XXXX-XXXX" className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm uppercase outline-none transition focus:border-cyan-400" />
              </label>
              <button type="button" onClick={() => void handleRedeem()} disabled={isRedeeming || !accessCode.trim()} className="inline-flex w-full items-center justify-center rounded-full bg-cyan-500 px-5 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60">
                {isRedeeming ? <Loader2 className="h-4 w-4 animate-spin" /> : "Redeem Access Code"}
              </button>
            </div>
          ) : status.can_access_app ? (
            <div className="space-y-5">
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Access Active
              </div>
              <h2 className="text-xl font-semibold tracking-tight">Your beta account is unlocked</h2>
              <p className="text-sm text-zinc-400">{status.message}</p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Link href={status.requires_byok_setup ? "/settings/api?setup=1" : "/dashboard"} className="inline-flex flex-1 items-center justify-center rounded-full bg-cyan-500 px-5 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-cyan-400">
                  {status.requires_byok_setup ? "Finish API & Keys Setup" : "Open Dashboard"}
                </Link>
                <Link href="/" className="inline-flex flex-1 items-center justify-center rounded-full border border-white/10 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/5">
                  Back to Home
                </Link>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <h2 className="text-xl font-semibold tracking-tight">Access unavailable</h2>
              <p className="text-sm text-zinc-400">{status?.message}</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
