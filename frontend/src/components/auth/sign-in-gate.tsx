/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import { Loader2, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { Checkbox } from "@/components/base/checkbox/checkbox";
import { CocomputerMark } from "@/components/brand/cocomputer-logo";
import { useAuth } from "@/lib/auth-context";

/**
 * Where to send the user once sign-in succeeds. Stashed in sessionStorage so a
 * page that also auto-redirects signed-in users (e.g. the marketing home) can
 * honour the original intent instead of racing it to `/app`.
 */
export const POST_SIGNIN_REDIRECT_KEY = "cc-post-signin-redirect";

export function readPostSignInRedirect(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(POST_SIGNIN_REDIRECT_KEY);
    if (value) window.sessionStorage.removeItem(POST_SIGNIN_REDIRECT_KEY);
    return value;
  } catch {
    return null;
  }
}

/**
 * Remember where a signed-out visitor was trying to go. Used by the app shell
 * when it bounces a deep link back to the marketing site.
 */
export function stashPostSignInRedirect(path: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, path);
  } catch {
    /* private mode — the visitor just lands on the default destination */
  }
}

type SignInRequest = {
  /** Short line explaining why the dialog appeared. */
  reason?: string;
  /** Path to open after a successful sign-in. */
  redirectTo?: string;
};

type SignInGateContextValue = {
  /** Open the sign-in dialog. No-op guard belongs to the caller. */
  requestSignIn: (request?: SignInRequest) => void;
};

const SignInGateContext = createContext<SignInGateContextValue | null>(null);

function GoogleGlyph() {
  return (
    <svg viewBox="0 0 18 18" className="size-4 shrink-0" aria-hidden>
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.88 2.69-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.34A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.94H.96a9 9 0 0 0 0 8.12l3.01-2.34Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.94l3.01 2.34C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}

export function SignInGateProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { signInWithGoogle } = useAuth();
  const [open, setOpen] = useState(false);
  const [request, setRequest] = useState<SignInRequest>({});
  const [accepted, setAccepted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestSignIn = useCallback((next: SignInRequest = {}) => {
    setRequest(next);
    setAccepted(false);
    setError(null);
    setIsSubmitting(false);
    setOpen(true);
  }, []);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      // Don't let a click-outside cancel an in-flight popup.
      if (isSubmitting && !nextOpen) return;
      setOpen(nextOpen);
    },
    [isSubmitting],
  );

  const handleSignIn = useCallback(async () => {
    if (!accepted || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);

    const redirectTo = request.redirectTo;
    if (redirectTo && typeof window !== "undefined") {
      try {
        window.sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, redirectTo);
      } catch {
        /* private mode — fall through to the direct push below */
      }
    }

    try {
      await signInWithGoogle();
      setOpen(false);
      if (redirectTo) router.replace(redirectTo);
    } catch (err) {
      if (typeof window !== "undefined") {
        try {
          window.sessionStorage.removeItem(POST_SIGNIN_REDIRECT_KEY);
        } catch {
          /* ignore */
        }
      }
      setError(
        err instanceof Error
          ? err.message
          : "Google sign-in failed. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [accepted, isSubmitting, request.redirectTo, router, signInWithGoogle]);

  const value = useMemo<SignInGateContextValue>(
    () => ({ requestSignIn }),
    [requestSignIn],
  );

  return (
    <SignInGateContext.Provider value={value}>
      {children}

      <Dialog.Root open={open} onOpenChange={handleOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in data-[state=closed]:fade-out" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-[71] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-3xl border border-zinc-200 bg-white p-7 shadow-2xl focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in data-[state=closed]:fade-out data-[state=open]:zoom-in-95 dark:border-white/10 dark:bg-[#141414]">
            <div className="mb-6 flex items-start justify-between gap-4">
              <CocomputerMark size={40} />
              <Dialog.Close
                className="rounded-lg p-1 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                aria-label="Close"
                disabled={isSubmitting}
              >
                <X className="size-4" />
              </Dialog.Close>
            </div>

            <Dialog.Title className="font-serif text-2xl leading-tight tracking-tight text-foreground">
              Sign in to continue
            </Dialog.Title>
            <Dialog.Description className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {request.reason ??
                "CoComputer boots an isolated Linux desktop for your account. Sign in with Google to start a session."}
            </Dialog.Description>

            <div className="mt-6 rounded-2xl border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-white/10 dark:bg-white/[0.02]">
              <div className="flex items-start gap-2">
                {/*
                  The label wraps only the box: the consent copy is almost all
                  policy links, and nesting them would toggle the checkbox on
                  every link click. `p-1.5 -m-1.5` grows the 16px box to a 28px
                  hit area so it clears the WCAG 2.5.8 24px minimum.
                */}
                <Checkbox
                  aria-labelledby="signin-terms-label"
                  isSelected={accepted}
                  onChange={setAccepted}
                  isDisabled={isSubmitting}
                  className="-m-1.5 shrink-0 rounded-lg p-1.5 transition-colors hover:bg-zinc-200/50 dark:hover:bg-white/5"
                />
                <span
                  id="signin-terms-label"
                  className="text-sm leading-relaxed text-muted-foreground"
                >
                  I agree to the{" "}
                  <Link
                    href="/terms"
                    className="font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
                  >
                    Terms of Service
                  </Link>
                  ,{" "}
                  <Link
                    href="/privacy"
                    className="font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
                  >
                    Privacy Policy
                  </Link>
                  , and{" "}
                  <Link
                    href="/acceptable-use"
                    className="font-medium text-blue-600 underline-offset-2 hover:underline dark:text-blue-400"
                  >
                    Acceptable Use Policy
                  </Link>
                  .
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => void handleSignIn()}
              disabled={!accepted || isSubmitting}
              className="mt-5 flex h-12 w-full items-center justify-center gap-3 rounded-full bg-zinc-900 text-sm font-medium text-white transition-all hover:bg-zinc-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-zinc-900 dark:bg-white dark:text-black dark:hover:bg-zinc-200 dark:disabled:hover:bg-white"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                  Signing in…
                </>
              ) : (
                <>
                  <GoogleGlyph />
                  Continue with Google
                </>
              )}
            </button>

            <p
              aria-live="polite"
              className="mt-3 min-h-[1.25rem] text-center text-xs text-muted-foreground"
            >
              {error ? (
                <span className="text-red-600 dark:text-red-400">{error}</span>
              ) : accepted ? (
                "A Google popup will open to finish sign-in."
              ) : (
                "Accept the policies above to enable sign-in."
              )}
            </p>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </SignInGateContext.Provider>
  );
}

export function useSignInGate() {
  const context = useContext(SignInGateContext);
  if (!context) {
    throw new Error("useSignInGate must be used within a SignInGateProvider");
  }
  return context;
}
