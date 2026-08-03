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
import { fetchBetaStatus } from "@/lib/beta-access";
import { Code2, Cpu, Layout, Mic, Shield, Terminal, Github } from "lucide-react";
import { BeamsBackground } from "@/components/react-bits/beams-background";
import { SiteNav } from "@/components/marketing/site-nav";

export default function HomePage() {
  const router = useRouter();
  const [isLaunching, setIsLaunching] = useState(false);
  const {
    user,
    isLoading: authLoading,
    signInWithGoogle,
    signOutUser,
  } = useAuth();
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
    let cancelled = false;
    async function maybeRedirectToBeta() {
      if (!user) return;
      try {
        const betaStatus = await fetchBetaStatus();
        if (cancelled) {
          return;
        }
        if (!betaStatus.can_access_app) {
          router.replace("/beta");
          return;
        }
        // Removed redirect to /settings/api as AppLayout or individual pages 
        // will now handle showing the settings modal instead.
      } catch {}
    }
    void maybeRedirectToBeta();
    return () => { cancelled = true; };
  }, [router, user]);

  const handleStart = async () => {
    if (!user) return;
    setIsLaunching(true);
    router.push("/session/new");
  };

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
          void signInWithGoogle().catch(() => {});
        }}
        onSignOut={() => {
          void signOutUser().catch(() => {});
        }}
        onStart={() => {
          void handleStart();
        }}
      />

      {/* Hero Section */}
      <section className="relative pt-40 pb-20 md:pt-56 md:pb-28 px-6 overflow-hidden">
        <BeamsBackground />

        <div className="relative z-10 max-w-4xl mx-auto text-center mt-4 md:mt-8">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="font-serif text-5xl sm:text-6xl md:text-7xl text-foreground tracking-tight mb-6 leading-[1.05] text-balance"
          >
            The agentic desktop for builders.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="max-w-2xl mx-auto text-base md:text-lg text-muted-foreground mb-10 leading-relaxed"
          >
            CoComputer turns what you say into real work on your desktop.
            <br className="hidden sm:block" />
            From research to shipping, it handles the busywork so you can stay
            focused.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="flex flex-col items-center gap-4"
          >
            <button
              onClick={() => (user ? handleStart() : signInWithGoogle())}
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
              alt="CoComputer product preview"
              className="w-full h-auto rounded-[12px] border border-sky-100/80 shadow-lg object-cover"
            />
          </div>
        </motion.div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-32 relative bg-background overflow-hidden">
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />

        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="text-center max-w-2xl mx-auto mb-20">
            <h2 className="text-blue-600 dark:text-blue-500 font-semibold text-xs mb-3 uppercase tracking-widest">Capabilities</h2>
            <h3 className="font-serif text-3xl md:text-5xl tracking-tight mb-6 text-foreground leading-tight">Engineered for absolute autonomy</h3>
            <p className="text-muted-foreground text-lg">A fully integrated architecture bridging Google&apos;s Agent Developer Kit and secure, transient cloud environments.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                title: "Voice-First Control",
                desc: "Talk to your desktop naturally. Powered by Gemini Live API for sub-second multimoal reasoning and response.",
                icon: <Mic className="w-5 h-5 text-blue-600 dark:text-blue-400" />,
                bg: "bg-blue-50 dark:bg-blue-900/20",
                border: "group-hover:border-blue-500/50"
              },
              {
                title: "E2B Cloud Sandboxes",
                desc: "Every session boots a secure, isolated Linux environment in milliseconds with full network and shell access.",
                icon: <BoxIcon className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />,
                bg: "bg-emerald-50 dark:bg-emerald-900/20",
                border: "group-hover:border-emerald-500/50"
              },
              {
                title: "Computer Control",
                desc: "UI navigation, terminal interaction, and visual feedback processing using the newest Agent Frameworks.",
                icon: <Layout className="w-5 h-5 text-purple-600 dark:text-purple-400" />,
                bg: "bg-purple-50 dark:bg-purple-900/20",
                border: "group-hover:border-purple-500/50"
              },
              {
                title: "Visual Telemetry",
                desc: "The agent sees what you see. Live screenshots are streamed directly to the model for perfect context.",
                icon: <CameraIcon className="w-5 h-5 text-orange-600 dark:text-orange-400" />,
                bg: "bg-orange-50 dark:bg-orange-900/20",
                border: "group-hover:border-orange-500/50"
              },
              {
                title: "Persistent History",
                desc: "Pick up right where you left off. All session metrics, files, and transcripts are securely state-managed.",
                icon: <HistoryIcon className="w-5 h-5 text-teal-600 dark:text-teal-400" />,
                bg: "bg-teal-50 dark:bg-teal-900/20",
                border: "group-hover:border-teal-500/50"
              },
              {
                title: "BYOK Security",
                desc: "Bring your own API keys. No vendor lock-in, with complete open-source transparency on your infrastructure.",
                icon: <Shield className="w-5 h-5 text-rose-600 dark:text-rose-400" />,
                bg: "bg-rose-50 dark:bg-rose-900/20",
                border: "group-hover:border-rose-500/50"
              }
            ].map((f, i) => (
              <motion.div 
                key={i}
                {...fadeInUp}
                className={`group relative p-8 rounded-3xl bg-card border border-card-border hover:shadow-xl transition-all duration-300 overflow-hidden ${f.border}`}
              >
                {/* Hover gradient effect inside card */}
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-gradient-to-br from-zinc-50 to-transparent dark:from-zinc-900 dark:to-transparent pointer-events-none" />
                
                <div className="relative z-10">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-6 shadow-sm ${f.bg}`}>
                    {f.icon}
                  </div>
                  <h4 className="font-serif text-xl text-foreground mb-3 tracking-tight">{f.title}</h4>
                  <p className="text-muted-foreground text-sm leading-relaxed">{f.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Stats Section with simple fade-in */}
      <section className="py-20 bg-background border-b border-zinc-100 dark:border-card-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[
              { label: "Execution Latency", value: "< 800ms", color: "text-blue-500", desc: "Sub-second response" },
              { label: "Sandbox Uptime", value: "99.99%", color: "text-emerald-500", desc: "Enterprise reliability" },
              { label: "Active Nodes", value: "2.4k+", color: "text-purple-500", desc: "Global infrastructure" },
              { label: "Success Rate", value: "98.2%", color: "text-orange-500", desc: "Task completion" },
            ].map((stat, i) => (
              <motion.div 
                key={i}
                initial={{ opacity: 0, y: 15 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                className="text-center md:text-left space-y-1"
              >
                <div className={`font-serif text-2xl md:text-3xl tracking-tight ${stat.color}`}>{stat.value}</div>
                <div className="text-xs font-bold uppercase tracking-widest text-zinc-400">{stat.label}</div>
                <div className="text-[10px] text-muted-foreground font-medium">{stat.desc}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* New: Technical Deep-Dive (Company scale details) */}
      <section id="how-it-works" className="py-32 bg-background overflow-hidden">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col lg:flex-row gap-20 items-center">
            <motion.div 
              initial={{ opacity: 0, x: -30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8 }}
              className="flex-1 space-y-8"
            >
              <h2 className="text-blue-600 font-semibold text-xs uppercase tracking-[0.2em]">The Core Protocol</h2>
              <h3 className="font-serif text-4xl md:text-5xl tracking-tight text-foreground leading-tight">
                Designed for the <br /> <span className="text-muted-foreground">Autonomous Era.</span>
              </h3>
              <p className="text-muted-foreground text-lg leading-relaxed">
                CoComputer isn&apos;t just a voice interface, it&apos;s a distributed neural network. We orchestrate the world&apos;s most advanced LLMs to drive real-time Linux kernels with near-zero latency, ensuring every command is precise, secure, and context-aware.
              </p>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-8 pt-4">
                {[
                  { t: "Neural Protocol", d: "Proprietary intent mapping to system syscalls." },
                  { t: "Native Sandbox", d: "Isolated, transient Ubuntu cloud instances." },
                  { t: "Visual Loop", d: "Sub-second frame analysis for UI navigation." },
                  { t: "Auto-Scale", d: "Global edge deployment for instant compute." }
                ].map((item, i) => (
                  <div key={i} className="space-y-2">
                    <h4 className="text-xs font-bold text-foreground uppercase tracking-widest flex items-center gap-2">
                      <div className="w-1 h-1 rounded-full bg-blue-500" />
                      {item.t}
                    </h4>
                    <p className="text-xs text-muted-foreground leading-relaxed font-medium">{item.d}</p>
                  </div>
                ))}
              </div>
            </motion.div>

            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8 }}
              className="flex-1 relative"
            >
              <div className="absolute inset-0 bg-blue-500/5 blur-[100px] rounded-full" />
              <div className="relative rounded-[2rem] border border-card-border bg-card p-8 shadow-2xl">
                <div className="space-y-6">
                   <div className="flex items-center justify-between border-b border-zinc-100 dark:border-card-border pb-4">
                      <div className="flex gap-1.5">
                         <div className="w-2.5 h-2.5 rounded-full bg-red-400/20" />
                         <div className="w-2.5 h-2.5 rounded-full bg-amber-400/20" />
                         <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/20" />
                      </div>
                      <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">Global_Status // OK</div>
                   </div>
                   <div className="space-y-4 pt-2">
                      <motion.div 
                        initial={{ width: "30%" }} 
                        whileInView={{ width: "90%" }} 
                        transition={{ duration: 1, delay: 0.5 }}
                        className="h-1.5 bg-blue-500 rounded-full" 
                      />
                      <div className="h-1.5 w-full bg-zinc-100 dark:bg-muted rounded-full" />
                      <div className="h-1.5 w-2/3 bg-zinc-100 dark:bg-muted rounded-full" />
                   </div>
                   <div className="pt-4 grid grid-cols-2 gap-4">
                      <div className="h-24 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-800 flex items-end p-4">
                         <div className="w-full space-y-2">
                            <div className="h-1 w-1/2 bg-blue-500/30 rounded-full" />
                            <div className="text-[8px] font-bold text-muted-foreground uppercase tracking-widest">Compute Load</div>
                         </div>
                      </div>
                      <div className="h-24 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-800 flex items-end p-4">
                         <div className="w-full space-y-2">
                            <div className="h-1 w-2/3 bg-emerald-500/30 rounded-full" />
                            <div className="text-[8px] font-bold text-muted-foreground uppercase tracking-widest">Neural Uplink</div>
                         </div>
                      </div>
                   </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* New: CTA Section */}
      <section className="py-24 px-6 relative overflow-hidden">
        <div className="max-w-5xl mx-auto">
          <motion.div 
            {...fadeInUp}
            className="relative rounded-[3rem] p-12 md:p-20 overflow-hidden text-center bg-blue-600 dark:bg-blue-600 shadow-2xl shadow-blue-500/20"
          >
            {/* Background pattern */}
            <div className="absolute inset-0 opacity-10 bg-[radial-gradient(circle_at_2px_2px,#fff_1px,transparent_0)] bg-[size:24px_24px]" />
            
            <div className="relative z-10">
              <h3 className="font-serif text-3xl md:text-5xl text-white mb-6">Experience the future of <br /> computer interaction.</h3>
              <p className="text-blue-100 text-lg mb-10 max-w-xl mx-auto text-balance">
                CoComputer is open for early access. Start building multimodal agents today with $0 setup costs.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                {mounted ? (
                  <>
                    <button
                      onClick={() => user ? handleStart() : signInWithGoogle()}
                      className="w-full sm:w-auto px-10 py-4 bg-white text-blue-600 rounded-xl font-bold hover:bg-zinc-100 transition-colors shadow-lg"
                    >
                      Get Started Now
                    </button>
                    <Link href="/docs" className="w-full sm:w-auto px-10 py-4 bg-blue-700/30 text-white border border-white/20 rounded-xl font-bold hover:bg-blue-700/50 transition-colors">
                      Read Documentation
                    </Link>
                  </>
                ) : (
                  // Render visually hidden placeholders on the server to keep
                  // markup stable until the client mounts.
                  <>
                    <button aria-hidden className="invisible w-full sm:w-auto px-10 py-4 bg-white text-blue-600 rounded-xl font-bold transition-colors shadow-lg">Get Started Now</button>
                    <div aria-hidden className="invisible w-full sm:w-auto px-10 py-4 bg-blue-700/30 text-white border border-white/20 rounded-xl font-bold">Read Documentation</div>
                  </>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-24 px-6 border-t border-zinc-100 dark:border-card-border bg-background relative z-20">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-12 gap-12 mb-16">
            <div className="col-span-2 md:col-span-4 space-y-6">
              <Link href="/" className="flex items-center gap-2 group">
                <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-lg shadow-blue-500/20">
                  <Terminal className="w-4 h-4" />
                </div>
                <span className="font-bold text-xl tracking-tighter text-foreground">CoComputer</span>
              </Link>
              <p className="text-muted-foreground text-sm leading-relaxed max-w-xs">
                Autonomous multimodal neural architecture bridging the gap between human language and native Linux environments.
              </p>
              <div className="flex items-center gap-4">
                <a href="https://x.com" className="text-muted-foreground hover:text-blue-500 transition-colors"><svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
                <a href="https://github.com" className="text-muted-foreground hover:text-foreground transition-colors"><Github className="w-5 h-5"/></a>
              </div>
            </div>

            <div className="col-span-1 md:col-span-2 space-y-4">
              <h5 className="text-xs font-bold uppercase tracking-widest text-foreground">Product</h5>
              <ul className="space-y-3 text-sm text-muted-foreground font-medium">
                <li className="hover:text-blue-500 transition-colors"><a href="#features">Features</a></li>
                <li className="hover:text-blue-500 transition-colors"><Link href="/pricing">Pricing</Link></li>
                <li className="hover:text-blue-500 transition-colors"><a href="#">Cloud Run</a></li>
                <li className="hover:text-blue-500 transition-colors"><a href="#">API Access</a></li>
              </ul>
            </div>

            <div className="col-span-1 md:col-span-2 space-y-4">
              <h5 className="text-xs font-bold uppercase tracking-widest text-foreground">Resources</h5>
              <ul className="space-y-3 text-sm text-muted-foreground font-medium">
                <li className="hover:text-blue-500 transition-colors"><a href="#">Documentation</a></li>
                <li className="hover:text-blue-500 transition-colors"><a href="#">Github</a></li>
                <li className="hover:text-blue-500 transition-colors"><a href="#">Devpost</a></li>
                <li className="hover:text-blue-500 transition-colors"><a href="#">Help Center</a></li>
              </ul>
            </div>

            <div className="col-span-2 md:col-span-4 space-y-4">
              <h5 className="text-xs font-bold uppercase tracking-widest text-foreground">Subscribe</h5>
              <p className="text-sm text-muted-foreground">Join 2,000+ developers building with CoComputer.</p>
              {mounted ? (
                <form className="flex gap-2" onSubmit={(e) => e.preventDefault()}>
                  <input 
                    type="email" 
                    placeholder="Enter your email" 
                    className="flex-1 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                  <button className="bg-zinc-900 dark:bg-white text-white dark:text-black px-4 py-2 rounded-lg text-sm font-bold hover:bg-zinc-800 transition-colors">
                    Join
                  </button>
                </form>
              ) : (
                // Server-render stable placeholders until client mounts to avoid
                // attribute injection (extensions) causing hydration mismatches.
                <div className="flex gap-2" aria-hidden>
                  <div className="flex-1 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-2 text-sm invisible">placeholder</div>
                  <div className="bg-zinc-900 dark:bg-white text-white dark:text-black px-4 py-2 rounded-lg text-sm font-bold invisible">Join</div>
                </div>
              )}
            </div>
          </div>
          
          <div className="pt-8 border-t border-zinc-100 dark:border-zinc-800/50 flex flex-col md:flex-row justify-between items-center gap-6 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
            <p>© {new Date().getFullYear()} CoComputer Systems. All rights reserved.</p>
            <div className="flex items-center gap-6">
              <a href="#" className="hover:text-zinc-900 dark:hover:text-white transition-colors">Privacy Policy</a>
              <a href="#" className="hover:text-zinc-900 dark:hover:text-white transition-colors">Terms of Service</a>
              <div className="flex items-center gap-2 text-emerald-500">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                SYSTEMS OPERATIONAL
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

// Temporary icon fallbacks for lucide-react if missing specific ones
function BoxIcon({ className }: { className?: string }) {
  return <Cpu className={className} />;
}
function CameraIcon({ className }: { className?: string }) {
  return <Code2 className={className} />;
}
function HistoryIcon({ className }: { className?: string }) {
  return <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
}
