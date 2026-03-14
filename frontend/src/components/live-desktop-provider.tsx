"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUpRight, MonitorSmartphone, X } from "lucide-react";

import { useToast } from "@/components/toast-provider";
import { useAuth } from "@/lib/auth-context";
import { useSession } from "@/lib/use-session";

type LiveDesktopSession = {
  sessionId: string;
  streamUrl: string;
};

type LiveDesktopContextValue = {
  activeDesktop: LiveDesktopSession | null;
  isMinimized: boolean;
  registerDesktop: (session: LiveDesktopSession) => void;
  minimizeDesktop: (session?: LiveDesktopSession) => void;
  restoreDesktop: () => void;
  clearDesktop: (sessionId?: string) => void;
  closeDesktop: () => Promise<void>;
};

const LiveDesktopContext = createContext<LiveDesktopContextValue | null>(null);

function LiveDesktopPiP({
  session,
  onRestore,
  onClose,
  isClosing,
}: {
  session: LiveDesktopSession;
  onRestore: () => void;
  onClose: () => Promise<void>;
  isClosing: boolean;
}) {
  return (
    <div className="fixed inset-x-3 bottom-3 z-40 sm:inset-x-auto sm:right-6 sm:bottom-6">
      <div className="w-full overflow-hidden rounded-[24px] border border-white/10 bg-[#050505]/95 shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur-xl sm:w-[380px]">
        <div className="flex items-center justify-between border-b border-white/10 bg-black/70 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-cyan-500/20 bg-cyan-500/10 text-cyan-300">
                <MonitorSmartphone className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-white">
                  Live Desktop
                </p>
                <p className="truncate text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                  Session {session.sessionId}
                </p>
              </div>
            </div>
          </div>

          <div className="ml-3 flex items-center gap-2">
            <button
              onClick={onRestore}
              className="inline-flex items-center gap-1 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-200 transition-colors hover:bg-cyan-500/20"
              title="Return to the live session"
            >
              <ArrowUpRight className="h-3.5 w-3.5" />
              Open
            </button>
            <button
              onClick={() => void onClose()}
              disabled={isClosing}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-red-500/20 bg-red-500/10 text-red-300 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              title="Close desktop session"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="relative aspect-[16/10] bg-black">
          {session.streamUrl ? (
            <>
              <iframe
                src={session.streamUrl}
                className="h-full w-full border-0 pointer-events-none"
                allow="clipboard-read; clipboard-write"
                title={`Desktop preview for ${session.sessionId}`}
              />
              <button
                onClick={onRestore}
                className="absolute inset-0 flex items-end justify-start bg-gradient-to-t from-black/60 via-black/5 to-transparent p-4 text-left transition-colors hover:from-black/70"
              >
                <span className="rounded-full border border-white/10 bg-black/70 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-white">
                  Return to live session
                </span>
              </button>
            </>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
              <div className="h-11 w-11 rounded-full border border-cyan-500/20 bg-cyan-500/10" />
              <div>
                <p className="text-sm font-semibold text-white">
                  Desktop stream is connecting
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  The live session is still running. Reopen it when you want the
                  full controls back.
                </p>
              </div>
            </div>
          )}

          <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-full border border-emerald-500/20 bg-black/60 px-3 py-1.5 backdrop-blur">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
            </span>
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-300">
              Running
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-white/10 bg-black/75 px-4 py-3">
          <p className="text-xs text-zinc-400">
            The desktop stays alive while you browse other pages.
          </p>
          <Link
            href={`/session/${session.sessionId}`}
            onClick={onRestore}
            className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300 transition-colors hover:text-cyan-200"
          >
            Resume
          </Link>
        </div>
      </div>
    </div>
  );
}

export function LiveDesktopProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { toast } = useToast();
  const { user } = useAuth();
  const { destroySession } = useSession();

  const [activeDesktop, setActiveDesktop] = useState<LiveDesktopSession | null>(
    null,
  );
  const [isMinimized, setIsMinimized] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const activeSessionIdRef = useRef<string | null>(null);

  const registerDesktop = useCallback((session: LiveDesktopSession) => {
    setActiveDesktop((current) => {
      if (
        current?.sessionId === session.sessionId &&
        current.streamUrl === session.streamUrl
      ) {
        return current;
      }

      return session;
    });

    if (activeSessionIdRef.current && activeSessionIdRef.current !== session.sessionId) {
      setIsMinimized(false);
    }

    activeSessionIdRef.current = session.sessionId;
  }, []);

  const minimizeDesktop = useCallback(
    (session?: LiveDesktopSession) => {
      if (session) {
        registerDesktop(session);
      }
      setIsMinimized(true);
    },
    [registerDesktop],
  );

  const restoreDesktop = useCallback(() => {
    if (!activeDesktop) {
      return;
    }

    setIsMinimized(false);

    if (pathname !== `/session/${activeDesktop.sessionId}`) {
      router.push(`/session/${activeDesktop.sessionId}`);
    }
  }, [activeDesktop, pathname, router]);

  const clearDesktop = useCallback((sessionId?: string) => {
    setActiveDesktop((current) => {
      if (!current) {
        return current;
      }

      if (!sessionId || current.sessionId === sessionId) {
        activeSessionIdRef.current = null;
        setIsMinimized(false);
        return null;
      }

      return current;
    });
  }, []);

  const closeDesktop = useCallback(async () => {
    if (!activeDesktop || isClosing) {
      return;
    }

    setIsClosing(true);

    try {
      const destroyed = await destroySession(activeDesktop.sessionId);
      if (!destroyed) {
        toast("Failed to close the desktop session.", "error");
        return;
      }

      const closedSessionId = activeDesktop.sessionId;
      activeSessionIdRef.current = null;
      setActiveDesktop(null);
      setIsMinimized(false);

      if (pathname === `/session/${closedSessionId}`) {
        router.push("/dashboard");
      }

      toast("Desktop session closed.", "success");
    } finally {
      setIsClosing(false);
    }
  }, [activeDesktop, destroySession, isClosing, pathname, router, toast]);

  useEffect(() => {
    if (!user) {
      activeSessionIdRef.current = null;
      setActiveDesktop(null);
      setIsMinimized(false);
    }
  }, [user]);

  const isShowingPiP =
    !!activeDesktop &&
    (isMinimized || pathname !== `/session/${activeDesktop.sessionId}`);

  const value = useMemo<LiveDesktopContextValue>(
    () => ({
      activeDesktop,
      isMinimized,
      registerDesktop,
      minimizeDesktop,
      restoreDesktop,
      clearDesktop,
      closeDesktop,
    }),
    [
      activeDesktop,
      clearDesktop,
      closeDesktop,
      isMinimized,
      minimizeDesktop,
      registerDesktop,
      restoreDesktop,
    ],
  );

  return (
    <LiveDesktopContext.Provider value={value}>
      {children}
      {activeDesktop && isShowingPiP ? (
        <LiveDesktopPiP
          session={activeDesktop}
          onRestore={restoreDesktop}
          onClose={closeDesktop}
          isClosing={isClosing}
        />
      ) : null}
    </LiveDesktopContext.Provider>
  );
}

export function useLiveDesktop() {
  const context = useContext(LiveDesktopContext);

  if (!context) {
    throw new Error("useLiveDesktop must be used within a LiveDesktopProvider");
  }

  return context;
}
