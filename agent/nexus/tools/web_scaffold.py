"""Tool for fast scaffolding of web prototypes and landing pages."""

from __future__ import annotations

import logging
from typing import Any

from nexus.tools.base import normalized_tool, tool_error, tool_success
from nexus.tools.docs import publish_html_artifact

logger = logging.getLogger(__name__)

_DEFAULT_LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .gradient-glow {{
      background: radial-gradient(circle at 50% 0%, rgba(99, 102, 241, 0.15) 0%, rgba(0, 0, 0, 0) 70%);
    }}
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen selection:bg-indigo-500 selection:text-white">
  <!-- Navigation -->
  <header class="border-b border-slate-800/80 backdrop-blur-md sticky top-0 z-50 bg-slate-950/80">
    <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
          ⚡
        </div>
        <span class="font-bold text-lg tracking-tight">{title}</span>
      </div>
      <nav class="hidden md:flex items-center gap-8 text-sm font-medium text-slate-300">
        <a href="#features" class="hover:text-white transition">Features</a>
        <a href="#pricing" class="hover:text-white transition">Pricing</a>
        <a href="#contact" class="hover:text-white transition">Contact</a>
      </nav>
      <div class="flex items-center gap-3">
        <a href="#contact" class="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 transition text-white shadow-md shadow-indigo-600/30">Get Started</a>
      </div>
    </div>
  </header>

  <!-- Hero Section -->
  <section class="gradient-glow pt-24 pb-20 px-6 text-center">
    <div class="max-w-4xl mx-auto">
      <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-xs font-semibold mb-6">
        <span>🚀 Next Generation Platform</span>
      </div>
      <h1 class="text-4xl sm:text-6xl font-extrabold tracking-tight text-white mb-6 leading-tight">
        Build smarter and faster with <span class="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-violet-300 to-indigo-200">{title}</span>
      </h1>
      <p class="text-lg sm:text-xl text-slate-400 mb-10 max-w-2xl mx-auto leading-relaxed">
        Empower your workflow with intelligent agents, seamless automation, and modern infrastructure designed for hyper-growth teams.
      </p>
      <div class="flex flex-col sm:flex-row items-center justify-center gap-4">
        <a href="#pricing" class="w-full sm:w-auto px-8 py-3.5 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white font-semibold shadow-xl shadow-indigo-500/25 transition transform active:scale-95">Start Free Trial</a>
        <a href="#features" class="w-full sm:w-auto px-8 py-3.5 rounded-xl border border-slate-800 hover:bg-slate-900 text-slate-300 font-medium transition">Explore Features</a>
      </div>
    </div>
  </section>

  <!-- Features Section -->
  <section id="features" class="py-24 px-6 max-w-7xl mx-auto">
    <div class="text-center mb-16">
      <h2 class="text-3xl font-bold text-white mb-4">Engineered for Scale & Speed</h2>
      <p class="text-slate-400 max-w-xl mx-auto">Everything you need to launch, manage, and scale intelligent applications effortlessly.</p>
    </div>
    <div class="grid md:grid-cols-3 gap-8">
      <div class="p-8 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:border-slate-700 transition">
        <div class="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center text-xl mb-6">🤖</div>
        <h3 class="text-xl font-bold text-white mb-2">Autonomous Agents</h3>
        <p class="text-slate-400 leading-relaxed text-sm">Self-healing agents that autonomously execute workflows, debug issues, and deploy code in isolated sandboxes.</p>
      </div>
      <div class="p-8 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:border-slate-700 transition">
        <div class="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-400 flex items-center justify-center text-xl mb-6">⚡</div>
        <h3 class="text-xl font-bold text-white mb-2">Instant Previews</h3>
        <p class="text-slate-400 leading-relaxed text-sm">Real-time hot-reloading previews let you review UI changes, API responses, and generated artifacts on the fly.</p>
      </div>
      <div class="p-8 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:border-slate-700 transition">
        <div class="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center text-xl mb-6">🛡️</div>
        <h3 class="text-xl font-bold text-white mb-2">Enterprise Security</h3>
        <p class="text-slate-400 leading-relaxed text-sm">Full policy-based controls, cryptographically signed audit logs, and isolated cloud micro-VMs.</p>
      </div>
    </div>
  </section>

  <!-- Pricing Section -->
  <section id="pricing" class="py-24 px-6 max-w-7xl mx-auto border-t border-slate-800/60">
    <div class="text-center mb-16">
      <h2 class="text-3xl font-bold text-white mb-4">Transparent, Predictable Pricing</h2>
      <p class="text-slate-400 max-w-xl mx-auto">Choose the tier that fits your stage, from solo builders to enterprise engineering teams.</p>
    </div>
    <div class="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
      <!-- Starter -->
      <div class="p-8 rounded-2xl border border-slate-800 bg-slate-900/30 flex flex-col justify-between">
        <div>
          <h3 class="text-lg font-semibold text-white mb-2">Starter</h3>
          <div class="text-4xl font-extrabold text-white mb-4">$0 <span class="text-sm font-normal text-slate-400">/mo</span></div>
          <p class="text-sm text-slate-400 mb-6">For individuals and open-source hobbyists.</p>
          <ul class="space-y-3 text-sm text-slate-300">
            <li class="flex items-center gap-2">✓ 1 Sandbox Instance</li>
            <li class="flex items-center gap-2">✓ Community Connectors</li>
            <li class="flex items-center gap-2">✓ Standard Cloud Compute</li>
          </ul>
        </div>
        <a href="#contact" class="mt-8 block text-center py-2.5 px-4 rounded-xl border border-slate-700 hover:bg-slate-800 text-sm font-medium transition">Get Started</a>
      </div>

      <!-- Pro -->
      <div class="p-8 rounded-2xl border-2 border-indigo-500 bg-gradient-to-b from-indigo-950/40 to-slate-900/40 relative flex flex-col justify-between shadow-2xl shadow-indigo-500/10">
        <div class="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-indigo-500 text-white text-xs font-semibold">POPULAR</div>
        <div>
          <h3 class="text-lg font-semibold text-white mb-2">Pro</h3>
          <div class="text-4xl font-extrabold text-white mb-4">$49 <span class="text-sm font-normal text-slate-400">/mo</span></div>
          <p class="text-sm text-slate-400 mb-6">For fast-growing startups and teams.</p>
          <ul class="space-y-3 text-sm text-slate-300">
            <li class="flex items-center gap-2">✓ Unlimited Sandboxes</li>
            <li class="flex items-center gap-2">✓ Multi-Agent Orchestration</li>
            <li class="flex items-center gap-2">✓ Real-Time Web Previews</li>
            <li class="flex items-center gap-2">✓ Dedicated GPU Accelerators</li>
          </ul>
        </div>
        <a href="#contact" class="mt-8 block text-center py-2.5 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-lg shadow-indigo-600/30 transition">Start Free Trial</a>
      </div>

      <!-- Enterprise -->
      <div class="p-8 rounded-2xl border border-slate-800 bg-slate-900/30 flex flex-col justify-between">
        <div>
          <h3 class="text-lg font-semibold text-white mb-2">Enterprise</h3>
          <div class="text-4xl font-extrabold text-white mb-4">Custom</div>
          <p class="text-sm text-slate-400 mb-6">For regulated industries and large orgs.</p>
          <ul class="space-y-3 text-sm text-slate-300">
            <li class="flex items-center gap-2">✓ VPC / On-Prem Deployment</li>
            <li class="flex items-center gap-2">✓ Custom Model Fine-Tuning</li>
            <li class="flex items-center gap-2">✓ 99.99% SLA & 24/7 Support</li>
          </ul>
        </div>
        <a href="#contact" class="mt-8 block text-center py-2.5 px-4 rounded-xl border border-slate-700 hover:bg-slate-800 text-sm font-medium transition">Contact Sales</a>
      </div>
    </div>
  </section>

  <!-- Contact / CTA Section -->
  <section id="contact" class="py-24 px-6 max-w-4xl mx-auto text-center border-t border-slate-800/60">
    <div class="p-12 rounded-3xl bg-gradient-to-b from-slate-900 to-slate-950 border border-slate-800/80 shadow-2xl">
      <h2 class="text-3xl sm:text-4xl font-extrabold text-white mb-4">Ready to accelerate your product?</h2>
      <p class="text-slate-400 mb-8 max-w-lg mx-auto">Join hundreds of visionary engineers building the autonomous software future today.</p>
      <form class="flex flex-col sm:flex-row gap-3 max-w-md mx-auto" onsubmit="event.preventDefault(); alert('Thank you! We will be in touch soon.');">
        <input type="email" placeholder="Enter your work email" required class="flex-1 px-4 py-3 rounded-xl bg-slate-800/80 border border-slate-700 text-white placeholder-slate-400 focus:outline-none focus:border-indigo-500 text-sm">
        <button type="submit" class="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 font-semibold text-white text-sm shadow-md shadow-indigo-600/30 transition">Get Started</button>
      </form>
    </div>
  </section>

  <!-- Footer -->
  <footer class="py-8 border-t border-slate-900 text-center text-xs text-slate-500">
    <p>© 2026 {title}. All rights reserved.</p>
  </footer>
</body>
</html>
"""


@normalized_tool
async def scaffold_web_project(
    title: str,
    template: str = "landing-page",
    description: str | None = None,
) -> dict[str, Any]:
    """Instantly scaffold a complete, responsive modern website or web prototype.

    Generates a full Tailwind/HTML single-page web app with navigation, hero,
    features, pricing, and contact sections, and immediately publishes it to the UI preview panel.

    Args:
        title: Title and brand name for the website.
        template: Template style (default: "landing-page").
        description: Optional brief description of the product or service.

    Returns:
        Result with the live preview URL and artifact metadata.
    """
    clean_title = (title or "Product Website").strip()
    html_doc = _DEFAULT_LANDING_PAGE.format(title=clean_title)

    res = await publish_html_artifact(
        title=f"{clean_title} - Website",
        html=html_doc,
        filename="index.html",
    )
    if res.get("status") == "success":
        url = res.get("detail", {}).get("url") or ""
        return tool_success(
            f"Successfully scaffolded and published website for '{clean_title}'. Live preview is ready in the Preview tab.",
            artifacts=[{"title": clean_title, "kind": "html", "url": url, "path": "outputs/index.html"}],
            detail=res.get("detail"),
        )
    return res
