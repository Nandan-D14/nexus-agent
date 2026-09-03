/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { motion, useScroll, useSpring } from "framer-motion";
import { useAuth } from "@/lib/auth-context";
import { listRecentSessions } from "@/lib/firestore-history";
import type { RecentSession } from "@/lib/message-types";
import { APP_CONNECTORS, APP_HOME } from "@/lib/app-paths";
import {
  Eye,
  KeyRound,
  Mic,
  Monitor,
  MousePointer2,
} from "lucide-react";
import { BeamsBackground } from "@/components/react-bits/beams-background";
import { SiteNav } from "@/components/marketing/site-nav";
import { SiteFooter } from "@/components/marketing/site-footer";
import { MarketingHeroPanel } from "@/components/marketing/marketing-hero-panel";
import { HeroAnnouncement } from "@/components/marketing/hero-announcement";
import { IntegrationsSection } from "@/components/marketing/integrations-section";
import {
  readPostSignInRedirect,
  useSignInGate,
} from "@/components/auth/sign-in-gate";
import { AppShellSkeleton } from "@/components/app-shell-skeleton";

export default function HomePage() {
  const router = useRouter();
  const [isLaunching, setIsLaunching] = useState(false);
  const [isCheckingAccess, setIsCheckingAccess] = useState(true);
  const {
    user,
    isLoading: authLoading,
    signOutUser,
  } = useAuth();
  const { requestSignIn } = useSignInGate();
  const [recentSessions, setRecentSessions] = useState<RecentSession[]>([]);
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 30,
    restDelta: 0.001
  });

  useEffect(() => {
    let cancelled = false;
    async function loadRecentSessions() {
      if (!user) { setRecentSessions([]); return; }
      try {
        const sessions = await listRecentSessions(user.uid);
        if (!cancelled) setRecentSessions(sessions);
      } catch { /* ignore */ }
    }
    void loadRecentSessions();
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (authLoading) {
      return;
    }
    if (!user) {
      setIsCheckingAccess(false);
      return;
    }
    setIsCheckingAccess(true);
    // Honour a gated destination (e.g. "Browse all connectors") over the default.
    router.replace(readPostSignInRedirect() ?? APP_HOME);
  }, [authLoading, router, user]);

  const handleStart = async () => {
    if (!user) return;
    setIsLaunching(true);
    router.push(APP_HOME);
  };

  /** Signed in → straight to the app. Signed out → consent dialog first. */
  const handlePrimaryCta = () => {
    if (user) {
      void handleStart();
      return;
    }
    // No explicit redirect: preserves any deep link the app shell stashed
    // when it bounced a signed-out visitor here. Falls back to APP_HOME.
    requestSignIn();
  };

  // Wait for auth before rendering marketing content so signed-in
  // users don't flash the landing page before redirecting.
  if (authLoading || isCheckingAccess) {
    return <AppShellSkeleton />;
  }

  const resumableSession = recentSessions.find((session) => session.can_continue_workspace);

  const fadeInUp = {
    initial: { opacity: 0, y: 20 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-50px" },
    transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] }
  };

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-blue-500/30 overflow-x-hidden font-sans">
      {/* Scroll Progress */}
      <motion.div
        className="fixed top-0 left-0 right-0 h-[2px] bg-blue-500 z-[60] origin-left"
        style={{ scaleX }}
      />

      <SiteNav
        variant="home"
        user={user}
        authLoading={authLoading}
        isLaunching={isLaunching}
        resumableSession={Boolean(resumableSession)}
        onSignIn={() => {
          requestSignIn();
        }}
        onSignOut={() => {
          void signOutUser().catch(() => {});
        }}
        onStart={() => {
          void handleStart();
        }}
      />

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 md:pt-40 md:pb-28 px-6 overflow-hidden">
        <BeamsBackground />

        <div className="relative z-10 max-w-4xl mx-auto text-center">
          <HeroAnnouncement />
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="font-serif text-5xl sm:text-6xl md:text-7xl text-foreground tracking-tight mb-6 leading-[1.05] text-balance"
          >
            Give an agent a real computer.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="mx-auto mb-10 max-w-2xl text-base leading-relaxed text-zinc-600 md:text-lg dark:text-zinc-300"
          >
            You talk. It actually does the work — on a real screen, not in a
            chat bubble.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="flex flex-col items-center gap-4"
          >
            <button
              onClick={handlePrimaryCta}
              disabled={isLaunching || authLoading}
              className="px-8 h-12 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-all active:scale-[0.98] disabled:opacity-50"
            >
              {isLaunching
                ? "Starting..."
                : authLoading
                  ? "Loading..."
                  : user
                    ? resumableSession
                      ? "Resume Workspace"
                      : "Launch Console"
                    : "Get Started"}
            </button>
          </motion.div>
        </div>

        {/* Hero product media */}
        <motion.div
          initial={{ opacity: 0, y: 100, scale: 0.95 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
          className="mt-20 max-w-6xl mx-auto relative"
        >
          <div className="absolute -inset-1 bg-gradient-to-r from-sky-300 to-blue-400 rounded-[16px] blur opacity-20" />
          <div className="relative rounded-[16px] border border-sky-100 bg-gradient-to-br from-white via-sky-50 to-sky-100 p-4 sm:p-6 md:p-8 shadow-2xl">
            <img
              src="/hero-product.png"
              alt="CoComputer session workspace with chat, live desktop, and agent tools"
              className="w-full h-auto rounded-[12px] border border-sky-100/80 shadow-lg object-cover"
            />
          </div>
        </motion.div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-32 relative bg-background overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />

        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="text-center max-w-2xl mx-auto mb-20">
            <h2 className="text-blue-600 dark:text-blue-500 font-semibold text-xs mb-3 uppercase tracking-widest">What you get</h2>
            <h3 className="font-serif text-3xl md:text-5xl tracking-tight mb-6 text-foreground leading-tight">A desktop the agent can actually use</h3>
            <p className="text-muted-foreground text-lg">Not a chat box that pretends to work. A real Linux environment with a screen, a shell, a browser, and the connectors you opt in.</p>
          </div>

          <div className="grid auto-rows-fr grid-cols-1 gap-3 md:grid-cols-6">
            <motion.article
              {...fadeInUp}
              className="group relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white p-7 md:col-span-4 md:row-span-2 md:p-8 dark:border-white/10 dark:bg-zinc-950"
            >
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(37,99,235,0.08),transparent_55%)]" />
              <div className="relative flex h-full min-h-[220px] flex-col">
                <span className="mb-5 inline-flex size-9 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200">
                  <Monitor className="size-4" />
                </span>
                <h4 className="font-serif text-2xl tracking-tight text-foreground md:text-3xl">
                  Isolated Linux desktop
                </h4>
                <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground md:text-base">
                  Every session boots a fresh cloud environment. Files, processes, and network stay in that sandbox — not a chat-only runner.
                </p>
                <div className="mt-auto pt-8 font-mono text-[11px] tracking-wide text-zinc-400">
                  session · isolated vm · linux
                </div>
              </div>
            </motion.article>

            <motion.article
              {...fadeInUp}
              className="relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white p-6 md:col-span-2 dark:border-white/10 dark:bg-zinc-950"
            >
              <span className="mb-4 inline-flex size-9 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200">
                <Eye className="size-4" />
              </span>
              <h4 className="font-serif text-lg tracking-tight text-foreground">
                The agent sees the screen
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Live desktop in the workspace. The agent looks at what is on screen before it clicks, types, or reports back.
              </p>
            </motion.article>

            <motion.article
              {...fadeInUp}
              className="relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white p-6 md:col-span-2 dark:border-white/10 dark:bg-zinc-950"
            >
              <span className="mb-4 inline-flex size-9 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200">
                <MousePointer2 className="size-4" />
              </span>
              <h4 className="font-serif text-lg tracking-tight text-foreground">
                Mouse, keyboard, terminal
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Click, type, and run shell commands on the desktop. The agent does work in the environment, not just generate text.
              </p>
            </motion.article>

            <motion.article
              {...fadeInUp}
              className="relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white p-6 md:col-span-3 dark:border-white/10 dark:bg-zinc-950"
            >
              <span className="mb-4 inline-flex size-9 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200">
                <Mic className="size-4" />
              </span>
              <h4 className="font-serif text-lg tracking-tight text-foreground">
                Talk or type
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Same session either way. Voice is available when you want it — it is not the whole product.
              </p>
            </motion.article>

            <motion.article
              {...fadeInUp}
              className="relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white p-6 md:col-span-3 dark:border-white/10 dark:bg-zinc-950"
            >
              <span className="mb-4 inline-flex size-9 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200">
                <KeyRound className="size-4" />
              </span>
              <h4 className="font-serif text-lg tracking-tight text-foreground">
                Your models, your keys
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Bring your own API keys. Choose the provider — you keep control of billing and model routing.
              </p>
            </motion.article>
          </div>
        </div>
      </section>

      <IntegrationsSection connectorsHref={APP_CONNECTORS} />

      <section id="how-it-works" className="py-32 bg-background overflow-hidden">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-blue-600 font-semibold text-xs uppercase tracking-[0.2em] mb-3">
              How it works
            </h2>
            <h3 className="font-serif text-4xl md:text-5xl tracking-tight text-foreground leading-tight mb-6">
              Session, work, keep.
            </h3>
            <p className="text-muted-foreground text-lg leading-relaxed">
              You talk in chat. The orchestrator drives an isolated desktop.
              You keep the artifacts — or start clean next time.
            </p>
          </div>

          <div className="relative mx-auto max-w-5xl">
            <div className="pointer-events-none absolute left-[16%] right-[16%] top-3 hidden h-px bg-zinc-200 md:block dark:bg-white/10" />
            <div className="grid gap-12 md:grid-cols-3 md:gap-8">
              {[
                {
                  step: "01",
                  title: "Session",
                  desc: "Chat and an isolated Linux desktop boot together. Nothing from other users shares that machine.",
                },
                {
                  step: "02",
                  title: "Work",
                  desc: "The agent sees the screen, clicks, types, runs the terminal, browses, and uses the connectors you enabled.",
                },
                {
                  step: "03",
                  title: "Keep",
                  desc: "Transcripts, files, and artifacts stay in history. Save a template, or start the next session clean.",
                },
              ].map((item) => (
                <div key={item.step} className="text-center md:pt-2">
                  <span className="relative z-10 mx-auto mb-6 flex size-6 items-center justify-center rounded-full bg-background font-mono text-[11px] text-zinc-400 ring-4 ring-background">
                    {item.step}
                  </span>
                  <h4 className="font-serif text-2xl tracking-tight text-foreground">
                    {item.title}
                  </h4>
                  <p className="mx-auto mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
                    {item.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-6 relative overflow-hidden">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeInUp}>
            <MarketingHeroPanel>
              <h3 className="font-serif text-3xl md:text-5xl text-white mb-6">
                Start a session. Get a desktop.
              </h3>
              <p className="text-blue-100 text-lg mb-10 max-w-xl mx-auto text-balance">
                Open CoComputer in the browser. No local install.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                {mounted ? (
                  <>
                    <button
                      onClick={handlePrimaryCta}
                      className="w-full sm:w-auto px-10 py-4 bg-white text-blue-600 rounded-xl font-bold hover:bg-zinc-100 transition-colors shadow-lg"
                    >
                      Get Started Now
                    </button>
                    <Link
                      href="#how-it-works"
                      className="w-full sm:w-auto px-10 py-4 bg-blue-700/30 text-white border border-white/20 rounded-xl font-bold hover:bg-blue-700/50 transition-colors"
                    >
                      See how it works
                    </Link>
                  </>
                ) : (
                  <>
                    <button
                      aria-hidden
                      className="invisible w-full sm:w-auto px-10 py-4 bg-white text-blue-600 rounded-xl font-bold transition-colors shadow-lg"
                    >
                      Get Started Now
                    </button>
                    <div
                      aria-hidden
                      className="invisible w-full sm:w-auto px-10 py-4 bg-blue-700/30 text-white border border-white/20 rounded-xl font-bold"
                    >
                      See how it works
                    </div>
                  </>
                )}
              </div>
            </MarketingHeroPanel>
          </motion.div>
        </div>
      </section>

      <SiteFooter showStatus />
    </div>
  );
}
