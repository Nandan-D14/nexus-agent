"use client";

import { motion } from "framer-motion";
import { Globe, Code2, BarChart3, Terminal, ArrowUpRight } from "lucide-react";

type Props = {
  onSelect: (text: string) => void;
  disabled: boolean;
};

type DemoScenario = {
  title: string;
  description: string;
  task: string;
  icon: React.ElementType;
  color: string;
};

const DEMOS: DemoScenario[] = [
  {
    title: "Web App Forge",
    description: "Initialize and deploy a live Flask microservice",
    task: "Create a simple Flask web app with a styled hello-world page. Install flask if needed, save the app to app.py, run it on port 5000 in the background, then use curl to verify it responds correctly.",
    icon: Globe,
    color: "text-blue-400",
  },
  {
    title: "Logic Architect",
    description: "Execute complex algorithmic computations in Python",
    task: "Write a Python script that generates the first 20 Fibonacci numbers and prints them as a neatly formatted table with the index and value columns. Save it to fibonacci.py, run it, and show the output.",
    icon: Code2,
    color: "text-indigo-400",
  },
  {
    title: "Data Visualizer",
    description: "Synthesize raw data into high-fidelity charts",
    task: "Using Python and matplotlib, create a colorful bar chart showing the popularity of programming languages (Python, JavaScript, TypeScript, Rust, Go, Java). Save the chart as chart.png and then take a screenshot so I can see it.",
    icon: BarChart3,
    color: "text-emerald-400",
  },
  {
    title: "System Auditor",
    description: "Full hardware and OS introspection and reporting",
    task: "Show me a complete system report: OS version, kernel, CPU model, total RAM, disk usage, list of running GUI applications, and the top 5 processes by memory usage. Format the output nicely.",
    icon: Terminal,
    color: "text-amber-400",
  },
];

export function DemoPicker({ onSelect, disabled }: Props) {
  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.08
      }
    }
  };

  const item = {
    hidden: { opacity: 0, y: 15 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.23, 1, 0.32, 1] } }
  };

  return (
    <motion.div 
      variants={container}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 px-2"
    >
      {DEMOS.map((demo) => (
        <motion.button
          variants={item}
          key={demo.title}
          type="button"
          onClick={() => onSelect(demo.task)}
          disabled={disabled}
          className={`
            group relative text-left p-5 rounded-[28px]
            border border-zinc-200/80 dark:border-white/8
            backdrop-blur-md transition-all duration-300
            focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40
            ${
              disabled
                ? "bg-zinc-100/50 dark:bg-white/[0.02] opacity-50 cursor-not-allowed"
                : "bg-white/80 dark:bg-white/[0.04] hover:bg-white dark:hover:bg-white/[0.08] hover:border-indigo-500/30 hover:shadow-[0_20px_40px_rgba(0,0,0,0.04)] dark:hover:shadow-none cursor-pointer active:scale-[0.97]"
            }
          `}
        >
          {/* Top Right Decoration */}
          {!disabled && (
            <div className="absolute top-5 right-5 text-zinc-300 dark:text-zinc-600 group-hover:text-indigo-500 dark:group-hover:text-indigo-400 transition-colors duration-300">
              <ArrowUpRight className="w-4 h-4" />
            </div>
          )}

          {/* Icon Container */}
          <div
            className={`
              w-12 h-12 rounded-2xl mb-5 flex items-center justify-center
              transition-all duration-500
              ${
                disabled
                  ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-600"
                  : "bg-zinc-50 dark:bg-zinc-900/50 group-hover:scale-110 group-hover:rotate-3 text-zinc-500 dark:text-zinc-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400"
              }
            `}
          >
            <demo.icon className="w-6 h-6" />
          </div>

          {/* Content */}
          <div className="space-y-2">
            <h3
              className={`font-semibold text-[15px] tracking-tight transition-colors duration-200 ${
                disabled
                  ? "text-zinc-400 dark:text-zinc-600"
                  : "text-zinc-900 dark:text-zinc-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400"
              }`}
            >
              {demo.title}
            </h3>

            <p
              className={`text-[12px] leading-relaxed transition-colors duration-200 ${
                disabled ? "text-zinc-400/60 dark:text-zinc-700" : "text-zinc-500 dark:text-zinc-400 group-hover:text-zinc-700 dark:group-hover:text-zinc-300"
              }`}
            >
              {demo.description}
            </p>
          </div>
          
          {/* Subtle Accent Gradient at bottom */}
          {!disabled && (
            <div className="absolute inset-x-8 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-indigo-500/40 to-transparent scale-x-0 group-hover:scale-x-100 transition-transform duration-700 ease-out" />
          )}
        </motion.button>
      ))}
    </motion.div>
  );
}
