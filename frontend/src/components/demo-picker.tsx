"use client";

import { motion } from "framer-motion";

type Props = {
  onSelect: (text: string) => void;
  disabled: boolean;
};

type DemoScenario = {
  title: string;
  description: string;
  task: string;
  icon: React.ReactNode;
};

const DEMOS: DemoScenario[] = [
  {
    title: "Web App Forge",
    description: "Initialize and deploy a live Flask microservice",
    task: "Create a simple Flask web app with a styled hello-world page. Install flask if needed, save the app to app.py, run it on port 5000 in the background, then use curl to verify it responds correctly.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <circle cx="12" cy="12" r="10" />
        <ellipse cx="12" cy="12" rx="4" ry="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
      </svg>
    ),
  },
  {
    title: "Logic Architect",
    description: "Execute complex algorithmic computations in Python",
    task: "Write a Python script that generates the first 20 Fibonacci numbers and prints them as a neatly formatted table with the index and value columns. Save it to fibonacci.py, run it, and show the output.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
        <line x1="14" y1="4" x2="10" y2="20" />
      </svg>
    ),
  },
  {
    title: "Data Visualizer",
    description: "Synthesize raw data into high-fidelity charts",
    task: "Using Python and matplotlib, create a colorful bar chart showing the popularity of programming languages (Python, JavaScript, TypeScript, Rust, Go, Java). Save the chart as chart.png and then take a screenshot so I can see it.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <rect x="3" y="12" width="4" height="8" rx="1" />
        <rect x="10" y="6" width="4" height="14" rx="1" />
        <rect x="17" y="3" width="4" height="17" rx="1" />
      </svg>
    ),
  },
  {
    title: "System Auditor",
    description: "Full hardware and OS introspection and reporting",
    task: "Show me a complete system report: OS version, kernel, CPU model, total RAM, disk usage, list of running GUI applications, and the top 5 processes by memory usage. Format the output nicely.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <polyline points="6 10 10 14 6 18" />
        <line x1="14" y1="18" x2="18" y2="18" />
      </svg>
    ),
  },
];

export function DemoPicker({ onSelect, disabled }: Props) {
  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } }
  };

  return (
    <motion.div 
      variants={container}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-100px" }}
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
    >
      {DEMOS.map((demo) => (
        <motion.button
          variants={item}
          key={demo.title}
          type="button"
          onClick={() => onSelect(demo.task)}
          disabled={disabled}
          className={`
            group relative text-left p-6 rounded-2xl
            border transition-all duration-300
            focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40
            ${
              disabled
                ? "bg-zinc-100/50 dark:bg-zinc-900/50 border-zinc-200/50 dark:border-zinc-800/50 opacity-50 cursor-not-allowed"
                : "bg-white/40 dark:bg-zinc-900/40 border-card-border dark:border-zinc-800 hover:border-cyan-500/50 hover:bg-zinc-50 dark:hover:bg-zinc-900/60 hover:shadow-[0_0_30px_rgba(34,211,238,0.05)] cursor-pointer active:scale-[0.98]"
            }
          `}
        >
          {/* Accent Glow */}
          {!disabled && (
            <div className="absolute top-0 right-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
              <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
            </div>
          )}

          {/* Icon Container */}
          <div
            className={`
              w-10 h-10 rounded-xl mb-4 flex items-center justify-center
              transition-all duration-300
              ${
                disabled
                  ? "bg-zinc-200 dark:bg-zinc-800 text-muted dark:text-zinc-600"
                  : "bg-zinc-100 dark:bg-zinc-800 group-hover:bg-cyan-500/10 dark:group-hover:bg-cyan-500/20 text-muted dark:text-zinc-400 group-hover:text-cyan-600 dark:group-hover:text-cyan-400"
              }
            `}
          >
            {demo.icon}
          </div>

          {/* Content */}
          <div className="space-y-1.5">
            <h3
              className={`font-bold text-sm tracking-tight transition-colors duration-200 ${
                disabled
                  ? "text-muted dark:text-zinc-500"
                  : "text-foreground dark:text-zinc-100 group-hover:text-black dark:group-hover:text-white"
              }`}
            >
              {demo.title}
            </h3>

            <p
              className={`text-[11px] leading-relaxed font-medium transition-colors duration-200 ${
                disabled ? "text-muted dark:text-zinc-700" : "text-zinc-500 dark:text-zinc-500 group-hover:text-foreground dark:group-hover:text-zinc-400"
              }`}
            >
              {demo.description}
            </p>
          </div>
          
          {/* Subtle line at bottom */}
          {!disabled && (
            <div className="absolute bottom-0 left-6 right-6 h-[1px] bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent scale-x-0 group-hover:scale-x-100 transition-transform duration-500" />
          )}
        </motion.button>
      ))}
    </motion.div>
  );
}
