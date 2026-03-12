"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DemoPicker } from "@/components/demo-picker";
import { useAuth } from "@/lib/auth-context";
import { listRecentSessions } from "@/lib/firestore-history";
import type { RecentSession } from "@/lib/message-types";
import { useSession } from "@/lib/use-session";

export default function HomePage() {
  const router = useRouter();
  const { createSession, isLoading, error } = useSession();
  const {
    user,
    isLoading: authLoading,
    error: authError,
    signInWithGoogle,
    signOutUser,
  } = useAuth();
  const [recentSessions, setRecentSessions] = useState<RecentSession[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadRecentSessions() {
      if (!user) {
        setRecentSessions([]);
        setHistoryError(null);
        return;
      }

      try {
        const sessions = await listRecentSessions(user.uid);
        if (!cancelled) {
          setRecentSessions(sessions);
          setHistoryError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setHistoryError(
            err instanceof Error ? err.message : "Failed to load recent sessions",
          );
        }
      }
    }

    void loadRecentSessions();

    return () => {
      cancelled = true;
    };
  }, [user]);

  const handleStart = async (demoCommand?: string) => {
    if (!user) return;

    const session = await createSession();
    if (session) {
      const params = demoCommand
        ? `?demo=${encodeURIComponent(demoCommand)}`
        : "";
      router.push(`/session/${session.session_id}${params}`);
    }
  };

  const activeError = error || authError || historyError;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="w-full max-w-4xl space-y-8">
        <div className="flex items-center justify-end">
          {user ? (
            <div className="flex items-center gap-3 rounded-full border border-[#27272a] bg-[#111113] px-3 py-1.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#27272a] text-xs font-semibold text-zinc-300">
                {(user.displayName || user.email || "U").slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-200">
                  {user.displayName || user.email || "Signed in"}
                </p>
                <p className="truncate text-xs text-zinc-500">
                  {user.email || "Firebase user"}
                </p>
              </div>
              <button
                onClick={() => {
                  void signOutUser().catch(() => {});
                }}
                className="rounded-lg border border-[#27272a] px-3 py-1.5 text-xs text-zinc-300 transition hover:border-zinc-500 hover:text-white"
              >
                Sign out
              </button>
            </div>
          ) : (
            <button
              onClick={() => {
                void signInWithGoogle().catch(() => {});
              }}
              disabled={authLoading}
              className="rounded-xl border border-[#22d3ee]/30 bg-[#111113] px-4 py-2 text-sm font-medium text-[#22d3ee] transition hover:border-[#22d3ee]/60 hover:bg-[#0f1720] disabled:opacity-50"
            >
              {authLoading ? "Loading..." : "Sign in with Google"}
            </button>
          )}
        </div>

        <div className="text-center space-y-2">
          <h1 className="text-5xl font-bold tracking-tight">
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400">
              NEXUS
            </span>
          </h1>
          <p className="text-zinc-400 text-lg">
            AI agent with full Linux desktop control
          </p>
          <p className="text-zinc-600 text-sm max-w-md mx-auto">
            Speak any task — research, coding, deployment, automation. NEXUS
            executes it autonomously on a live Linux computer.
          </p>
        </div>

        <div className="flex justify-center">
          <button
            onClick={() => handleStart()}
            disabled={isLoading || !user || authLoading}
            className="px-8 py-3 rounded-xl bg-gradient-to-r from-cyan-600 to-emerald-600
              text-white font-medium text-sm
              hover:from-cyan-500 hover:to-emerald-500
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-all shadow-lg shadow-cyan-600/20"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                Booting Desktop...
              </span>
            ) : user ? (
              "Start Session"
            ) : (
              "Sign in to Start"
            )}
          </button>
        </div>

        {activeError && (
          <p className="text-red-400 text-sm text-center">{activeError}</p>
        )}

        {!user && !authLoading && (
          <p className="mx-auto max-w-lg text-center text-sm text-zinc-500">
            Sign in with Google to create secure sessions, reconnect to active
            runs, and browse your saved history from Firestore.
          </p>
        )}

        <div className="space-y-3">
          <p className="text-zinc-500 text-xs text-center uppercase tracking-wider">
            Or try a demo scenario
          </p>
          <DemoPicker
            onSelect={(cmd) => handleStart(cmd)}
            disabled={isLoading || !user}
          />
        </div>

        <div className="rounded-2xl border border-[#27272a] bg-[#111113] p-5">
          <div className="mb-4">
            <p className="text-sm font-semibold text-zinc-200">
              Recent Sessions
            </p>
            <p className="text-xs text-zinc-500">
              Firestore-backed history for your signed-in account.
            </p>
          </div>

          {!user ? (
            <p className="text-sm text-zinc-500">
              Sign in to load your archived sessions.
            </p>
          ) : recentSessions.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No saved sessions yet. Start one to create your archive.
            </p>
          ) : (
            <div className="space-y-3">
              {recentSessions.map((session) => (
                <Link
                  key={session.session_id}
                  href={`/session/${session.session_id}`}
                  className="block rounded-xl border border-[#27272a] bg-[#18181b] p-4 transition hover:border-[#22d3ee]/40 hover:bg-[#171719]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-100">
                        {session.title}
                      </p>
                      <p className="truncate text-xs text-zinc-500">
                        {session.summary || "No summary yet"}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[11px] uppercase tracking-wider text-zinc-500">
                        {session.status}
                      </p>
                      <p className="text-[11px] text-zinc-600">
                        {session.updated_at
                          ? new Date(session.updated_at).toLocaleString()
                          : "Recently created"}
                      </p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-center gap-3 text-[10px] text-zinc-600 uppercase tracking-wider">
          <span>Firebase Auth</span>
          <span className="text-zinc-800">|</span>
          <span>Firestore</span>
          <span className="text-zinc-800">|</span>
          <span>Gemini Live API</span>
          <span className="text-zinc-800">|</span>
          <span>Google ADK</span>
          <span className="text-zinc-800">|</span>
          <span>E2B Desktop</span>
          <span className="text-zinc-800">|</span>
          <span>Cloud Run</span>
        </div>
      </div>
    </div>
  );
}
