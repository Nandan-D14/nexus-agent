/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { motion } from "framer-motion";
import {
  Check,
  ChevronDown,
  ArrowRight,
  Zap,
  Shield,
  Cpu,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { APP_DASHBOARD } from "@/lib/app-paths";
import { SiteNav } from "@/components/marketing/site-nav";
import { SiteFooter } from "@/components/marketing/site-footer";
import { MarketingHeroPanel } from "@/components/marketing/marketing-hero-panel";

const plans = [
  {
    name: "Free",
    price: { monthly: 0, annual: 0 },
    description: "Explore CoComputer with basic access.",
    icon: <Zap className="w-5 h-5 text-zinc-500" />,
    iconBg: "bg-zinc-100 dark:bg-zinc-800",
    cta: "Get Started",
    ctaHref: "/",
    popular: false,
    features: [
      "10 sessions per month",
      "15 min sandbox per session",
      "BYOK / your models",
      "Web search & terminal tools",
      "Community support",
      "Session history (7 days)",
    ],
  },
  {
    name: "Pro",
    price: { monthly: 29, annual: 24 },
    description: "Full power for developers and researchers.",
    icon: <Cpu className="w-5 h-5 text-blue-600 dark:text-blue-400" />,
    iconBg: "bg-blue-50 dark:bg-blue-900/20",
    cta: "Start Pro Trial",
    ctaHref: "/",
    popular: true,
    features: [
      "Unlimited sessions",
      "2 hour sandbox per session",
      "BYOK / your models",
      "All tools + Google Workspace integrations",
      "Priority email support",
      "Full session history",
      "Playwright browser automation",
      "Custom MCP servers",
    ],
  },
  {
    name: "Enterprise",
    price: { monthly: null, annual: null },
    description: "Custom infrastructure for teams at scale.",
    icon: <Shield className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />,
    iconBg: "bg-emerald-50 dark:bg-emerald-900/20",
    cta: "Contact Sales",
    ctaHref: "/",
    popular: false,
    features: [
      "Everything in Pro",
      "Custom sandbox duration & resources",
      "Priority model routing & fallbacks",
      "Custom tool integrations & MCP",
      "Dedicated support engineer",
      "SSO & team management",
      "SLA guarantees",
      "On-premise deployment option",
    ],
  },
];

const faqs = [
  {
    question: "What happens when I exceed my free tier sessions?",
    answer:
      "You'll receive a notification at 8 sessions. Once you hit the limit, new sessions are paused until your next billing cycle. You can upgrade to Pro anytime for unlimited access.",
  },
  {
    question: "How does sandbox isolation work?",
    answer:
      "Every session boots a fresh, isolated cloud environment with full Linux access. Your files, processes, and network are completely sandboxed. Nothing persists between sessions unless you explicitly save to your workspace.",
  },
  {
    question: "Can I use my own API keys?",
    answer:
      "Yes. CoComputer uses a BYOK (Bring Your Own Key) model. You connect your own API keys for the providers you choose. Keys are stored encrypted in your session config — you keep control of billing and routing.",
  },
  {
    question: "What's included in Enterprise support?",
    answer:
      "Enterprise includes a dedicated support engineer, custom SLA guarantees, priority model routing with guaranteed uptime, SSO/team management, and optional on-premise deployment. Contact us for a tailored plan.",
  },
  {
    question: "Can I switch plans anytime?",
    answer:
      "Yes. Upgrade or downgrade at any time. When upgrading, you get immediate access to Pro features. Downgrades take effect at the end of your current billing cycle.",
  },
];

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-zinc-100 dark:border-card-border">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-6 text-left group"
      >
        <span className="text-base font-semibold text-foreground group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors pr-4">
          {question}
        </span>
        <ChevronDown
          className={`w-5 h-5 text-muted-foreground shrink-0 transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        />
      </button>
      <motion.div
        initial={false}
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="overflow-hidden"
      >
        <p className="pb-6 text-sm text-muted-foreground leading-relaxed">
          {answer}
        </p>
      </motion.div>
    </div>
  );
}

export default function PricingPage() {
  const { user, signInWithGoogle } = useAuth();
  const [annual, setAnnual] = useState(false);
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const fadeInUp = {
    initial: { opacity: 0, y: 20 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-50px" },
    transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] },
  };

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-blue-500/30 overflow-x-hidden font-sans">
      <SiteNav
        variant="pricing"
        user={user}
        onSignIn={() => {
          void signInWithGoogle().catch(() => {});
        }}
      />

      {/* Hero */}
      <section className="relative pt-32 pb-16 px-6">
        <div className="absolute inset-0 z-0 pointer-events-none flex items-center justify-center">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-blue-500/10 dark:bg-blue-500/20 blur-[120px] rounded-full" />
        </div>
        <div className="relative z-10 max-w-3xl mx-auto text-center">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="text-4xl md:text-6xl font-bold tracking-tight text-foreground mb-4 leading-[1.1]"
          >
            Simple, transparent pricing
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-muted-foreground text-lg mb-10 max-w-xl mx-auto"
          >
            Start free, scale when you need. No hidden fees, no surprises.
          </motion.p>

          {/* Billing Toggle */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="inline-flex items-center gap-3 rounded-full bg-zinc-100 dark:bg-zinc-900 p-1 border border-zinc-200 dark:border-card-border"
          >
            <button
              onClick={() => setAnnual(false)}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-all ${
                !annual
                  ? "bg-white dark:bg-zinc-800 text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setAnnual(true)}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-2 ${
                annual
                  ? "bg-white dark:bg-zinc-800 text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Annual
              <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30 px-2 py-0.5 rounded-full">
                Save 20%
              </span>
            </button>
          </motion.div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="py-12 px-6">
        <div className="max-w-6xl mx-auto grid md:grid-cols-3 gap-6">
          {plans.map((plan, i) => (
            <motion.div
              key={plan.name}
              {...fadeInUp}
              transition={{ ...fadeInUp.transition, delay: i * 0.1 }}
              className={`relative group rounded-3xl p-8 flex flex-col ${
                plan.popular
                  ? "bg-card border-2 border-blue-500 dark:border-blue-500/50 shadow-xl shadow-blue-500/10"
                  : "bg-card border border-card-border"
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-blue-600 text-white text-xs font-bold rounded-full">
                  Most Popular
                </div>
              )}

              <div className="mb-6">
                <div
                  className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-4 ${plan.iconBg}`}
                >
                  {plan.icon}
                </div>
                <h3 className="text-xl font-bold text-foreground">
                  {plan.name}
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {plan.description}
                </p>
              </div>

              <div className="mb-8">
                {plan.price.monthly !== null ? (
                  <div className="flex items-baseline gap-1">
                    <span className="text-4xl font-bold text-foreground">
                      $
                      {annual
                        ? plan.price.annual
                        : plan.price.monthly}
                    </span>
                    {plan.price.monthly > 0 && (
                      <span className="text-sm text-muted-foreground">
                        /mo
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="text-4xl font-bold text-foreground">
                    Custom
                  </div>
                )}
                {annual && plan.price.monthly !== null && plan.price.monthly > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">
                    billed annually (${plan.price.annual * 12}/yr)
                  </p>
                )}
              </div>

              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-start gap-3 text-sm text-foreground"
                  >
                    <Check
                      className={`w-4 h-4 mt-0.5 shrink-0 ${
                        plan.popular
                          ? "text-blue-600 dark:text-blue-400"
                          : "text-emerald-600 dark:text-emerald-400"
                      }`}
                    />
                    {feature}
                  </li>
                ))}
              </ul>

              <Link
                href={plan.ctaHref}
                className={`w-full py-3 rounded-xl text-sm font-medium text-center transition-all flex items-center justify-center gap-2 ${
                  plan.popular
                    ? "bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-500/20"
                    : "bg-zinc-100 dark:bg-white/5 border border-zinc-200 dark:border-white/10 text-foreground hover:bg-zinc-200 dark:hover:bg-white/10"
                }`}
              >
                {plan.cta}
                <ArrowRight className="w-4 h-4" />
              </Link>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Feature Comparison */}
      <section className="py-24 px-6">
        <div className="max-w-4xl mx-auto">
          <motion.div {...fadeInUp} className="text-center mb-16">
            <h2 className="mb-4 font-serif text-3xl tracking-tight text-foreground md:text-4xl">
              Compare plans
            </h2>
            <p className="text-muted-foreground">
              See what&apos;s included in each tier.
            </p>
          </motion.div>

          <motion.div {...fadeInUp}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 dark:border-card-border">
                    <th className="text-left py-4 pr-4 font-semibold text-foreground">
                      Feature
                    </th>
                    <th className="text-center py-4 px-4 font-semibold text-muted-foreground">
                      Free
                    </th>
                    <th className="text-center py-4 px-4 font-semibold text-blue-600 dark:text-blue-400">
                      Pro
                    </th>
                    <th className="text-center py-4 pl-4 font-semibold text-muted-foreground">
                      Enterprise
                    </th>
                  </tr>
                </thead>
                <tbody className="text-foreground">
                  {[
                    { feature: "Sessions", free: "10/mo", pro: "Unlimited", enterprise: "Unlimited" },
                    { feature: "Sandbox duration", free: "15 min", pro: "2 hours", enterprise: "Custom" },
                    { feature: "Models", free: "BYOK", pro: "BYOK", enterprise: "BYOK + priority" },
                    { feature: "Web search", free: true, pro: true, enterprise: true },
                    { feature: "Terminal & code", free: true, pro: true, enterprise: true },
                    { feature: "Computer control", free: false, pro: true, enterprise: true },
                    { feature: "Google Workspace", free: false, pro: true, enterprise: true },
                    { feature: "Browser automation", free: false, pro: true, enterprise: true },
                    { feature: "Custom MCP servers", free: false, pro: true, enterprise: true },
                    { feature: "Team management", free: false, pro: false, enterprise: true },
                    { feature: "SSO", free: false, pro: false, enterprise: true },
                    { feature: "SLA guarantee", free: false, pro: false, enterprise: true },
                    { feature: "Support", free: "Community", pro: "Priority email", enterprise: "Dedicated" },
                  ].map((row) => (
                    <tr
                      key={row.feature}
                      className="border-b border-zinc-100 dark:border-card-border/50"
                    >
                      <td className="py-3 pr-4 font-medium">{row.feature}</td>
                      {[row.free, row.pro, row.enterprise].map((val, i) => (
                        <td
                          key={i}
                          className={`py-3 ${i === 0 ? "text-center px-4" : i === 1 ? "text-center px-4" : "text-center pl-4"}`}
                        >
                          {val === true ? (
                            <Check className="w-4 h-4 mx-auto text-emerald-600 dark:text-emerald-400" />
                          ) : val === false ? (
                            <span className="text-zinc-300 dark:text-zinc-700">
                              —
                            </span>
                          ) : (
                            <span className="text-muted-foreground">
                              {val}
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-24 px-6 bg-zinc-50/50 dark:bg-zinc-900/20">
        <div className="max-w-3xl mx-auto">
          <motion.div {...fadeInUp} className="text-center mb-12">
            <h2 className="mb-4 font-serif text-3xl tracking-tight text-foreground md:text-4xl">
              Frequently asked questions
            </h2>
            <p className="text-muted-foreground">
              Everything you need to know about CoComputer pricing.
            </p>
          </motion.div>

          <motion.div {...fadeInUp}>
            {faqs.map((faq) => (
              <FAQItem
                key={faq.question}
                question={faq.question}
                answer={faq.answer}
              />
            ))}
          </motion.div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6 relative overflow-hidden">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeInUp}>
            <MarketingHeroPanel>
              <h3 className="font-serif text-3xl md:text-5xl text-white mb-6">
                Ready to get started?
              </h3>
              <p className="text-blue-100 text-lg mb-10 max-w-xl mx-auto text-balance">
                Join thousands of developers building with CoComputer. Start
                free, upgrade when you need more power.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                {mounted ? (
                  <>
                    <button
                      onClick={() =>
                        user
                          ? (window.location.href = APP_DASHBOARD)
                          : signInWithGoogle()
                      }
                      className="w-full sm:w-auto px-10 py-4 bg-white text-blue-600 rounded-xl font-bold hover:bg-zinc-100 transition-colors shadow-lg"
                    >
                      {user ? "Go to Dashboard" : "Start Free"}
                    </button>
                    <Link
                      href="/"
                      className="w-full sm:w-auto px-10 py-4 bg-blue-700/30 text-white border border-white/20 rounded-xl font-bold hover:bg-blue-700/50 transition-colors"
                    >
                      Back to Home
                    </Link>
                  </>
                ) : (
                  <>
                    <button
                      aria-hidden
                      className="invisible w-full sm:w-auto px-10 py-4 bg-white text-blue-600 rounded-xl font-bold shadow-lg"
                    >
                      Start Free
                    </button>
                    <div
                      aria-hidden
                      className="invisible w-full sm:w-auto px-10 py-4 bg-blue-700/30 text-white border border-white/20 rounded-xl font-bold"
                    >
                      Back to Home
                    </div>
                  </>
                )}
              </div>
            </MarketingHeroPanel>
          </motion.div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
