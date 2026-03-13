"use client";

import { Terminal, Key, Copy, Check, RefreshCw } from "lucide-react";
import { useState } from "react";

export default function APISettingsPage() {
  const [copied, setCopied] = useState(false);
  const apiKey = "nx_live_xxxxxxxxxxxxxxxxxxxxxxxx";

  const handleCopy = () => {
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h2 className="text-xl font-black uppercase tracking-widest text-white mb-2">API & Developer</h2>
        <p className="text-sm text-zinc-500">Access tokens for programmatic control.</p>
      </div>

      <div className="space-y-6">
        <div className="p-6 rounded-2xl bg-black border border-white/10 space-y-4">
          <div className="flex items-center gap-3 text-cyan-400">
            <Key className="w-5 h-5" />
            <h3 className="font-bold uppercase tracking-widest text-sm">Personal Access Token</h3>
          </div>
          <p className="text-sm text-zinc-400">Use this token to authenticate requests to the Nexus API. Do not share it.</p>
          
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-white/5 border border-white/10 rounded-xl p-3 font-mono text-zinc-300 relative group overflow-hidden">
              <div className="absolute inset-0 bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity" />
              {apiKey}
            </div>
            <button 
              onClick={handleCopy}
              className="p-3 bg-white/10 hover:bg-white/20 border border-white/10 rounded-xl transition-all text-white flex items-center justify-center shrink-0"
              title="Copy to clipboard"
            >
              {copied ? <Check className="w-5 h-5 text-emerald-400" /> : <Copy className="w-5 h-5" />}
            </button>
            <button 
              className="p-3 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-xl transition-all flex items-center justify-center shrink-0 text-red-400"
              title="Revoke and Generate New"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="p-6 rounded-2xl bg-white/[0.02] border border-white/5 space-y-4">
          <div className="flex items-center gap-3 text-white">
            <Terminal className="w-5 h-5 text-zinc-500" />
            <h3 className="font-bold uppercase tracking-widest text-sm">Automated Webhooks</h3>
          </div>
          <p className="text-sm text-zinc-400">Receive POST requests when sessions complete or encounter critical errors.</p>
          
          <input 
            type="text" 
            placeholder="https://your-server.com/webhooks/nexus"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 transition-colors font-mono text-sm"
          />
        </div>
      </div>
    </div>
  );
}
