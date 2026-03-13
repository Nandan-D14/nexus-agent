"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/use-session";
import { DemoPicker } from "@/components/demo-picker";
import { useState, useEffect } from "react";
import { motion, useScroll, useTransform, useSpring, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/auth-context";
import { listRecentSessions } from "@/lib/firestore-history";
import type { RecentSession } from "@/lib/message-types";

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
  const [scrolled, setScrolled] = useState(false);
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 30,
    restDelta: 0.001
  });

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

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

  const fadeInUp = {
    initial: { opacity: 0, y: 30 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-100px" },
    transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] }
  };

  const staggerContainer = {
    initial: {},
    whileInView: { transition: { staggerChildren: 0.1, delayChildren: 0.2 } },
    viewport: { once: true, margin: "-100px" }
  };

  return (
    <div className="min-h-screen bg-[#030303] text-white selection:bg-cyan-500/30 overflow-x-hidden">
      {/* Scroll Progress Indicator */}
      <motion.div
        className="fixed top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-cyan-500 to-emerald-500 z-[60] origin-left"
        style={{ scaleX }}
      />

      {/* Navigation */}
      <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 px-8 py-5 ${scrolled ? "bg-black/60 backdrop-blur-xl border-b border-white/5" : "bg-transparent"}`}>
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center gap-3 group cursor-pointer"
          >
            <div className="relative">
              <div className="absolute inset-0 bg-cyan-500/20 blur-lg group-hover:bg-cyan-500/40 transition-all duration-500 rounded-full" />
              <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-emerald-400 flex items-center justify-center shadow-lg transform group-hover:rotate-6 transition-transform">
                <span className="text-black font-black text-2xl italic">N</span>
              </div>
            </div>
            <span className="text-2xl font-black tracking-tighter italic uppercase group-hover:text-cyan-400 transition-colors">Nexus</span>
          </motion.div>
          
          <div className="hidden lg:flex items-center gap-10 text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-400">
            {["Capabilities", "Operation", "Missions", "API"].map((item) => (
              <a 
                key={item} 
                href={`#${item.toLowerCase()}`} 
                className="hover:text-cyan-400 transition-all relative group py-2"
              >
                {item}
                <span className="absolute bottom-0 left-0 w-full h-[1px] bg-cyan-500 scale-x-0 group-hover:scale-x-100 transition-transform origin-right group-hover:origin-left duration-300" />
              </a>
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center gap-4"
          >
            {user ? (
              <>
                <span className="hidden md:inline text-[10px] font-bold text-zinc-400 uppercase tracking-widest truncate max-w-[120px]">
                  {user.displayName || user.email}
                </span>
                <button
                  onClick={() => { void signOutUser().catch(() => {}); }}
                  className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white/20 transition-all"
                >
                  Sign out
                </button>
                <Link
                  href="/dashboard"
                  className="hidden md:flex px-4 py-2 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white/20 transition-all items-center"
                >
                  Dashboard
                </Link>
                <Link
                  href="/settings/profile"
                  className="hidden md:flex px-4 py-2 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white/20 transition-all items-center"
                >
                  Settings
                </Link>
                <button
                  onClick={() => handleStart()}
                  disabled={isLoading}
                  className="px-6 py-2.5 rounded-full bg-white text-black text-[11px] font-black uppercase tracking-widest hover:bg-cyan-400 transition-all active:scale-95 disabled:opacity-50 shadow-xl shadow-white/5"
                >
                  {isLoading ? "Booting..." : "Launch Console"}
                </button>
              </>
            ) : (
              <button
                onClick={() => { void signInWithGoogle().catch(() => {}); }}
                disabled={authLoading}
                className="px-6 py-2.5 rounded-full bg-white text-black text-[11px] font-black uppercase tracking-widest hover:bg-cyan-400 transition-all active:scale-95 disabled:opacity-50 shadow-xl shadow-white/5"
              >
                {authLoading ? "Loading..." : "Sign In"}
              </button>
            )}
          </motion.div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center pt-20 px-8 overflow-hidden">
        {/* Dynamic Background Elements */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <motion.div 
            animate={{ 
              scale: [1, 1.2, 1],
              opacity: [0.1, 0.15, 0.1],
              rotate: [0, 45, 0]
            }}
            transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
            className="absolute top-[-20%] left-[-10%] w-[80%] h-[80%] bg-cyan-500/10 rounded-full blur-[160px]" 
          />
          <motion.div 
            animate={{ 
              scale: [1, 1.3, 1],
              opacity: [0.1, 0.12, 0.1],
              rotate: [0, -30, 0]
            }}
            transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
            className="absolute bottom-[-20%] right-[-10%] w-[80%] h-[80%] bg-emerald-500/10 rounded-full blur-[160px]" 
          />
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#8080800a_1px,transparent_1px),linear-gradient(to_bottom,#8080800a_1px,transparent_1px)] bg-[size:40px_40px] mask-radial opacity-40" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto flex flex-col items-center text-center">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-3 px-5 py-2 rounded-full bg-white/5 border border-white/10 backdrop-blur-md mb-12"
          >
            <div className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_10px_rgba(34,211,238,0.8)] animate-pulse" />
            <span className="text-[11px] font-bold uppercase tracking-[0.3em] text-zinc-300">v2.5 Hybrid Intelligence Protocol</span>
          </motion.div>
          
          <motion.h1 
            initial={{ opacity: 0, filter: "blur(20px)", scale: 0.95 }}
            animate={{ opacity: 1, filter: "blur(0px)", scale: 1 }}
            transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            className="text-5xl md:text-8xl font-black tracking-tighter leading-[0.9] italic mb-10"
          >
            <span className="block text-gradient">COMMAND THE</span>
            <span className="block text-accent-gradient drop-shadow-[0_0_50px_rgba(34,211,238,0.2)]">AUTONOMOUS.</span>
          </motion.h1>

          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 1 }}
            className="max-w-3xl mx-auto text-zinc-400 text-xl md:text-2xl font-light leading-relaxed mb-12"
          >
            Nexus is a multimodal neural orchestrator for Linux environments. 
            Speak, and it executes — from complex devops to recursive web exploration.
          </motion.p>

          <motion.div 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6, duration: 1 }}
            className="flex flex-col items-center gap-6"
          >
            <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
              <button
                onClick={() => handleStart()}
                disabled={isLoading || !user || authLoading}
                className="group relative px-12 py-6 rounded-2xl bg-white text-black font-black text-xs uppercase tracking-[0.2em] overflow-hidden transition-all hover:scale-105 active:scale-95 shadow-2xl shadow-white/5"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-400 to-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <span className="relative z-10 flex items-center gap-3">
                  {isLoading ? "Initializing Mission..." : user ? "Start Neural Session" : "Sign in to Start"}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="w-5 h-5 group-hover:translate-x-1 transition-transform duration-300">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </span>
              </button>
              <a href="#missions" className="group px-12 py-6 rounded-2xl bg-white/5 border border-white/10 text-white font-bold text-xs uppercase tracking-[0.2em] hover:bg-white/10 transition-all flex items-center gap-2">
                Mission Profiles
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4 text-zinc-500 group-hover:translate-y-1 transition-transform">
                  <path d="M19 14l-7 7-7-7M12 3v18" />
                </svg>
              </a>
            </div>

            {error && (
              <motion.p 
                initial={{ opacity: 0 }} 
                animate={{ opacity: 1 }} 
                className="mt-4 text-red-400 text-[10px] font-black uppercase tracking-[0.3em]"
              >
                Initialization Failure: {error}
              </motion.p>
            )}
          </motion.div>
        </div>

        {/* Floating Mockup (Scroll-linked Parallax) */}
        <motion.div 
          style={{ y: useTransform(scrollYProgress, [0, 0.2], [0, -100]) }}
          className="absolute bottom-[-10%] left-1/2 -translate-x-1/2 w-full max-w-6xl px-8 pointer-events-none"
        >
          <div className="relative glass-panel rounded-3xl p-3 shadow-[0_0_100px_rgba(0,0,0,1)] group">
            <div className="absolute inset-0 bg-gradient-to-t from-[#030303] via-transparent to-transparent z-10" />
            <div className="flex items-center gap-2 px-6 py-4 border-b border-white/5">
              <div className="flex gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500/20" />
                <div className="w-3 h-3 rounded-full bg-amber-500/20" />
                <div className="w-3 h-3 rounded-full bg-emerald-500/20" />
              </div>
              <div className="mx-auto text-[11px] font-bold text-zinc-600 uppercase tracking-[0.5em]">nexus_control_surface_v2.5</div>
            </div>
            <div className="aspect-[21/9] bg-black relative flex items-center justify-center overflow-hidden rounded-b-2xl">
              <div className="absolute inset-0 opacity-40 bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.3),transparent_70%)]" />
              <div className="text-center space-y-6">
                <motion.div 
                  animate={{ scale: [1, 1.1, 1], opacity: [0.6, 1, 0.6] }}
                  transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                  className="w-24 h-24 rounded-full border border-cyan-500/30 flex items-center justify-center mx-auto"
                >
                  <div className="w-6 h-6 rounded-full bg-cyan-500 shadow-[0_0_30px_rgba(34,211,238,1)]" />
                </motion.div>
                <div className="space-y-2">
                  <p className="text-[12px] font-mono text-cyan-500 uppercase tracking-[0.5em] font-black">Neural Uplink Active</p>
                  <div className="h-1 w-48 bg-zinc-900 mx-auto rounded-full overflow-hidden">
                    <motion.div 
                      animate={{ x: [-192, 192] }}
                      transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                      className="h-full w-full bg-cyan-500/40" 
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      {/* Capabilities Section */}
      <section id="capabilities" className="py-40 px-8 relative overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <motion.div 
            {...fadeInUp}
            className="max-w-2xl mb-24 space-y-6"
          >
            <h2 className="text-xs font-black text-cyan-500 uppercase tracking-[0.5em]">Capabilities</h2>
            <h3 className="text-5xl md:text-7xl font-black italic tracking-tighter uppercase leading-[0.9]">
              The Architecture of <br /> <span className="text-gradient">Total Autonomy.</span>
            </h3>
            <p className="text-zinc-500 text-lg font-medium leading-relaxed">
              Nexus isn&apos;t just a chatbot; it&apos;s a fully-integrated pilot for a high-performance Linux kernel.
            </p>
          </motion.div>

          <motion.div 
            variants={staggerContainer}
            initial="initial"
            whileInView="whileInView"
            viewport={{ once: true, margin: "-100px" }}
            className="grid grid-cols-1 md:grid-cols-3 gap-8"
          >
            {[
              {
                title: "Multimodal Synthesis",
                description: "Seamlessly integrates high-fidelity speech recognition with real-time visual analysis of the desktop environment.",
                icon: <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              },
              {
                title: "Isolated Sandbox",
                description: "Deploy missions within secure, transient E2B Desktop sandboxes. Zero persistent threat, full environment control.",
                icon: <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              },
              {
                title: "ADK Core V2",
                description: "Built on the Google Agent Developer Kit, utilizing optimized hybrid reasoning models for low-latency decision making.",
                icon: <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              }
            ].map((feature, idx) => (
              <motion.div 
                key={idx}
                variants={fadeInUp}
                className="glass-card group p-10 rounded-[2.5rem] relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-20 transition-opacity">
                  <span className="text-8xl font-black italic select-none">0{idx + 1}</span>
                </div>
                <div className="relative z-10 space-y-8">
                  <div className="w-14 h-14 rounded-2xl bg-white/5 flex items-center justify-center text-zinc-400 group-hover:bg-cyan-500/20 group-hover:text-cyan-400 transition-all duration-500 shadow-inner">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-7 h-7">
                      {feature.icon}
                      {idx === 0 && <><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="22" /></>}
                      {idx === 1 && <path d="M7 11V7a5 5 0 0 1 10 0v4" />}
                    </svg>
                  </div>
                  <div className="space-y-4">
                    <h4 className="text-xl font-black italic uppercase tracking-tight text-white group-hover:text-cyan-400 transition-colors">{feature.title}</h4>
                    <p className="text-zinc-500 text-base leading-relaxed font-medium">{feature.description}</p>
                  </div>
                  <div className="pt-4 flex items-center gap-2 text-[10px] font-black text-cyan-500 uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-all transform translate-y-4 group-hover:translate-y-0">
                    System Verified <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
                  </div>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* Operation Section (Scroll-linked progress) */}
      <section id="operation" className="py-40 px-8 bg-white/[0.01] border-y border-white/5 relative">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-32 items-center">
          <div className="space-y-20">
            <motion.div {...fadeInUp} className="space-y-6">
              <h2 className="text-xs font-black text-emerald-500 uppercase tracking-[0.5em]">The Protocol</h2>
              <h3 className="text-5xl md:text-7xl font-black italic tracking-tighter uppercase leading-[0.9]">
                Fluid <br /> <span className="text-gradient">Intelligence.</span>
              </h3>
            </motion.div>
            
            <motion.div 
              variants={staggerContainer}
              initial="initial"
              whileInView="whileInView"
              viewport={{ once: true }}
              className="space-y-12"
            >
              {[
                { n: "01", t: "Neural Initiation", d: "Nexus establishes a high-bandwidth uplink via voice or JSON-RPC. Intent is mapped across neural clusters for optimal resource routing." },
                { n: "02", t: "Sandbox Synthesis", d: "A dedicated kernel environment is spun up within 800ms. Tools are hot-loaded based on the specific mission profile." },
                { n: "03", t: "Recursive Optimization", d: "Agent performs continuous self-correction using visual and textual telemetry, ensuring mission finality without manual oversight." }
              ].map((step, i) => (
                <motion.div key={i} variants={fadeInUp} className="flex gap-10 group">
                  <span className="text-5xl font-black italic text-zinc-900 group-hover:text-cyan-500/40 transition-colors duration-700 select-none">
                    {step.n}
                  </span>
                  <div className="space-y-3">
                    <h4 className="text-lg font-black uppercase tracking-widest text-zinc-200 group-hover:text-white transition-colors">{step.t}</h4>
                    <p className="text-zinc-500 text-sm leading-relaxed font-medium max-w-sm">{step.d}</p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </div>
          
          <motion.div 
            initial={{ opacity: 0, x: 40 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
            className="relative h-[600px]"
          >
            <div className="absolute inset-0 bg-cyan-500/10 rounded-full blur-[160px] animate-pulse" />
            <div className="relative h-full glass-panel rounded-[3rem] p-10 border border-white/10 flex flex-col shadow-2xl">
              <div className="flex items-center justify-between mb-10">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-cyan-500/20 flex items-center justify-center">
                    <div className="w-2 h-2 rounded-full bg-cyan-500 animate-ping" />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest leading-none mb-1">Telemetry Uplink</span>
                    <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-widest leading-none animate-pulse">Live // Stream_88-X</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <div className="h-4 w-[1px] bg-zinc-800" />
                  <span className="text-[10px] font-mono text-zinc-600">88.293-AZ</span>
                </div>
              </div>

              <div className="flex-1 space-y-6 font-mono text-[11px] leading-relaxed overflow-hidden">
                <AnimatePresence>
                  {[
                    { c: "> CONNECTING_NEURAL_UPLINK...", col: "text-cyan-500" },
                    { c: "> ANALYZING_USER_INTENT: 'DEPLOY MICROSERVICE'", col: "text-zinc-400" },
                    { c: "> BOOTING_KERNAL_VM_IMAGE: E2B-LINUX-G2", col: "text-zinc-500" },
                    { c: "> PROGRESS: [████████████░░░░] 74%", col: "text-cyan-500/50" },
                    { c: "> SANDBOX_ACTIVE: ID_882_99_X", col: "text-emerald-500" },
                    { c: "> RUNNING: pip install flask --quiet", col: "text-zinc-400" },
                    { c: "> OPENING_PORT: 5000 (LOCAL_UPLINK)", col: "text-zinc-400" },
                    { c: "> SYSTEM_READY. AWAITING_TRANSCRIPT...", col: "text-cyan-500 animate-pulse" },
                  ].map((line, idx) => (
                    <motion.p 
                      key={idx}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 1 + idx * 0.2 }}
                      className={line.col}
                    >
                      {line.c}
                    </motion.p>
                  ))}
                </AnimatePresence>
              </div>

              <div className="mt-10 pt-10 border-t border-white/5 flex items-center justify-between">
                <div className="flex gap-6">
                  <div className="flex flex-col">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-1">CPU LOAD</span>
                    <span className="text-zinc-400 font-mono text-xs">14.2%</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-1">LATENCY</span>
                    <span className="text-emerald-500 font-mono text-xs">22MS</span>
                  </div>
                </div>
                <div className="w-24 h-8 bg-zinc-900/50 rounded-lg flex items-center justify-center border border-white/5">
                   <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <motion.div animate={{ width: ["10%", "90%", "40%"] }} transition={{ duration: 4, repeat: Infinity }} className="h-full bg-cyan-500" />
                   </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Missions (Missions) */}
      <section id="missions" className="py-40 px-8 relative">
        <div className="max-w-7xl mx-auto">
          <motion.div 
            {...fadeInUp}
            className="text-center mb-24 space-y-6"
          >
            <h2 className="text-xs font-black text-cyan-500 uppercase tracking-[0.5em]">Operations</h2>
            <h3 className="text-6xl md:text-8xl font-black italic tracking-tighter uppercase leading-none">
              Mission <span className="text-gradient">Profiles.</span>
            </h3>
            <p className="text-zinc-500 text-lg font-medium leading-relaxed max-w-xl mx-auto">
              Select a pre-configured mission profile or initialize a custom command sequence.
            </p>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 1 }}
            className="max-w-6xl mx-auto"
          >
            <DemoPicker
              onSelect={(cmd) => handleStart(cmd)}
              disabled={isLoading || !user}
            />
          </motion.div>
        </div>
      </section>

      {/* API Section */}
      <section id="api" className="py-40 px-8 relative overflow-hidden">
        <div className="max-w-5xl mx-auto">
          <motion.div 
            whileHover={{ scale: 1.01 }}
            className="glass-panel rounded-[3rem] p-16 relative overflow-hidden border border-white/10 text-center"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 via-transparent to-emerald-500/10 opacity-40" />
            <div className="relative z-10 space-y-10">
              <h3 className="text-4xl md:text-6xl font-black italic tracking-tighter uppercase">Universal <span className="text-gradient">Expansion.</span></h3>
              <p className="text-zinc-400 text-lg leading-relaxed max-w-2xl mx-auto">
                Nexus is built for scale. Access the full power of the neural orchestrator via our high-bandwidth API, allowing for integrated autonomous agents in your own ecosystem.
              </p>
              <div className="flex justify-center gap-6">
                <button className="px-10 py-4 rounded-xl bg-white text-black font-black text-[11px] uppercase tracking-widest hover:bg-cyan-400 transition-all shadow-xl shadow-white/5">
                  Request API Access
                </button>
                <button className="px-10 py-4 rounded-xl bg-white/5 border border-white/10 text-white font-black text-[11px] uppercase tracking-widest hover:bg-white/10 transition-all">
                  Read Documentation
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Recent Sessions */}
      {user && recentSessions.length > 0 && (
        <section className="py-20 px-8 relative">
          <div className="max-w-4xl mx-auto">
            <motion.div {...fadeInUp} className="space-y-6">
              <h2 className="text-xs font-black text-emerald-500 uppercase tracking-[0.5em]">History</h2>
              <h3 className="text-3xl font-black italic tracking-tighter uppercase">Recent Sessions</h3>
            </motion.div>
            <div className="mt-8 space-y-3">
              {recentSessions.map((session) => (
                <Link
                  key={session.session_id}
                  href={`/session/${session.session_id}`}
                  className="block rounded-xl border border-white/5 bg-white/[0.02] p-4 transition hover:border-cyan-500/30 hover:bg-white/[0.04]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-zinc-200">{session.title}</p>
                      <p className="truncate text-xs text-zinc-500">{session.summary || "No summary yet"}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{session.status}</p>
                      <p className="text-[10px] text-zinc-600">
                        {session.updated_at ? new Date(session.updated_at).toLocaleString() : "Recently created"}
                      </p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Footer */}
      <footer className="pt-40 pb-20 px-8 border-t border-white/5 relative bg-[#030303]">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-20">
          <div className="md:col-span-2 space-y-8">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center">
                <span className="text-black font-black text-2xl italic">N</span>
              </div>
              <span className="text-2xl font-black tracking-tighter italic uppercase">Nexus</span>
            </div>
            <p className="text-zinc-500 text-sm font-medium leading-relaxed max-w-sm uppercase tracking-wider">
              Autonomous Multimodal Neural Architecture. Built for the next era of computational intelligence.
            </p>
            <div className="flex gap-4">
               {["X", "GH", "DC", "LI"].map(s => (
                 <div key={s} className="w-10 h-10 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-[10px] font-black text-zinc-500 hover:text-white hover:border-white/20 transition-all cursor-pointer">{s}</div>
               ))}
            </div>
          </div>
          
          <div className="space-y-8">
            <h5 className="text-[11px] font-black uppercase tracking-[0.4em] text-white">Ecosystem</h5>
            <ul className="space-y-4 text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">
              <li className="hover:text-cyan-400 transition-colors"><a href="#">Gemini 2.5 Flash</a></li>
              <li className="hover:text-cyan-400 transition-colors"><a href="#">Google ADK Core</a></li>
              <li className="hover:text-cyan-400 transition-colors"><a href="#">E2B Desktop V2</a></li>
              <li className="hover:text-cyan-400 transition-colors"><a href="#">Cloud Run Infra</a></li>
            </ul>
          </div>

          <div className="space-y-8">
            <h5 className="text-[11px] font-black uppercase tracking-[0.4em] text-white">Resources</h5>
            <ul className="space-y-4 text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">
              <li className="hover:text-cyan-400 transition-colors"><a href="#">Documentation</a></li>
              <li className="hover:text-cyan-400 transition-colors"><a href="#">Github Repo</a></li>
              <li className="hover:text-cyan-400 transition-colors"><a href="#">Hackathon Info</a></li>
              <li className="hover:text-cyan-400 transition-colors"><a href="#">System Status</a></li>
            </ul>
          </div>
        </div>
        
        <div className="max-w-7xl mx-auto mt-40 pt-10 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-6 text-[9px] font-black text-zinc-600 uppercase tracking-[0.4em]">
          <p>© 2026 NEXUS SYSTEMS ARCHITECTURE // ALL RIGHTS RESERVED</p>
          <p className="flex items-center gap-4">
            <span>Security Protocol v9.2.0</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span>Encrypted Neural Link</span>
          </p>
        </div>
      </footer>
    </div>
  );
}
