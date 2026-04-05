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
  const panelRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    originX: number;
    originY: number;
    startX: number;
    startY: number;
  } | null>(null);
  const didPositionRef = useRef(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  const clampPosition = useCallback((x: number, y: number) => {
    if (typeof window === "undefined") {
      return { x, y };
    }

    const width = panelRef.current?.offsetWidth ?? 320;
    const height = panelRef.current?.offsetHeight ?? 248;
    const padding = window.innerWidth < 640 ? 12 : 20;
    const maxX = Math.max(padding, window.innerWidth - width - padding);
    const maxY = Math.max(padding, window.innerHeight - height - padding);

    return {
      x: Math.min(Math.max(padding, x), maxX),
      y: Math.min(Math.max(padding, y), maxY),
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const updatePosition = () => {
      const width = panelRef.current?.offsetWidth ?? 320;
      const height = panelRef.current?.offsetHeight ?? 248;
      const padding = window.innerWidth < 640 ? 12 : 20;

      if (!didPositionRef.current) {
        didPositionRef.current = true;
        setPosition(
          clampPosition(
            window.innerWidth - width - padding,
            window.innerHeight - height - padding,
          ),
        );
        return;
      }

      setPosition((current) => clampPosition(current.x, current.y));
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);

    return () => {
      window.removeEventListener("resize", updatePosition);
    };
  }, [clampPosition, session.sessionId]);

  const handleDragStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) {
        return;
      }

      dragStateRef.current = {
        pointerId: event.pointerId,
        originX: position.x,
        originY: position.y,
        startX: event.clientX,
        startY: event.clientY,
      };

      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [position.x, position.y],
  );

  const handleDragMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!dragStateRef.current || dragStateRef.current.pointerId !== event.pointerId) {
        return;
      }

      const deltaX = event.clientX - dragStateRef.current.startX;
      const deltaY = event.clientY - dragStateRef.current.startY;
      setPosition(
        clampPosition(
          dragStateRef.current.originX + deltaX,
          dragStateRef.current.originY + deltaY,
        ),
      );
    },
    [clampPosition],
  );

  const handleDragEnd = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current || dragStateRef.current.pointerId !== event.pointerId) {
      return;
    }

    dragStateRef.current = null;

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  return (
    <div
      className="fixed left-0 top-0 z-40"
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
    >
      <div
        ref={panelRef}
        className="w-[min(320px,calc(100vw-24px))] overflow-hidden rounded-[28px] border border-black/8 bg-white/78 shadow-[0_30px_80px_rgba(15,23,42,0.18)] backdrop-blur-2xl dark:border-white/10 dark:bg-neutral-950/78 dark:shadow-[0_30px_80px_rgba(0,0,0,0.45)]"
      >
        <div className="flex items-center gap-3 px-4 py-3">
          <button
            onClick={() => void onClose()}
            disabled={isClosing}
            className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-[#ff5f57] shadow-[0_0_0_1px_rgba(0,0,0,0.08)] transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-50"
            title="Close desktop session"
          >
            <X className="h-2.5 w-2.5 text-black/60 opacity-0 transition-opacity hover:opacity-100" />
          </button>

          <div
            onPointerDown={handleDragStart}
            onPointerMove={handleDragMove}
            onPointerUp={handleDragEnd}
            onPointerCancel={handleDragEnd}
            className="flex min-w-0 flex-1 cursor-grab items-center gap-3 rounded-2xl px-2 py-1.5 active:cursor-grabbing"
            title="Drag to move"
          >
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-black/5 text-zinc-700 dark:bg-white/10 dark:text-zinc-200">
              <MonitorSmartphone className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-900 dark:text-white">
                Live Desktop
              </p>
              <p className="truncate text-[11px] text-zinc-500 dark:text-zinc-400">
                Running now • drag to move
              </p>
            </div>
          </div>

          <button
            onClick={onRestore}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-zinc-900 px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
            title="Return to the live session"
          >
            <ArrowUpRight className="h-3.5 w-3.5" />
            Open
          </button>
        </div>

        <div className="px-3 pb-3">
          <button
            onClick={onRestore}
            className="group relative block w-full overflow-hidden rounded-[22px] border border-black/6 bg-[#eef1f5] text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition-transform hover:scale-[1.01] dark:border-white/10 dark:bg-black/35 dark:shadow-none"
          >
            <div className="relative aspect-[16/10] overflow-hidden">
              {session.streamUrl ? (
                <iframe
                  src={session.streamUrl}
                  className="h-full w-full border-0 pointer-events-none"
                  allow="clipboard-read; clipboard-write"
                  title={`Desktop preview for ${session.sessionId}`}
                />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
                  <div className="h-10 w-10 rounded-full bg-black/6 dark:bg-white/10" />
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-white">
                      Connecting desktop
                    </p>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      The session is still alive. Open it when you need the full
                      controls.
                    </p>
                  </div>
                </div>
              )}

              <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-white/15 opacity-80 dark:from-black/45 dark:to-white/5" />

              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-3 p-3">
                <div className="inline-flex items-center gap-2 rounded-full bg-white/82 px-3 py-1.5 text-[11px] font-medium text-zinc-700 shadow-sm dark:bg-black/55 dark:text-zinc-200">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Session {session.sessionId}
                </div>
                <span className="inline-flex items-center rounded-full bg-black/72 px-3 py-1.5 text-[11px] font-medium text-white opacity-90 transition-opacity group-hover:opacity-100">
                  Resume
                </span>
              </div>
            </div>
          </button>
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
