"use client";

import { Save, Loader2, Bell, Mail, AlertTriangle } from "lucide-react";
import { useState } from "react";

export default function NotificationsSettingsPage() {
  const [saving, setSaving] = useState(false);
  const [prefs, setPrefs] = useState({
    sessionEnd: true,
    errors: true,
    weeklyDigest: false,
    marketing: false,
  });

  const handleSave = async () => {
    setSaving(true);
    // Future: implement PATCH
    setTimeout(() => {
      setSaving(false);
      alert("Notification preferences saved");
    }, 1000);
  };

  const Toggle = ({ label, desc, checked, onChange, icon: Icon, colorClass }: any) => (
    <div className="flex items-start justify-between p-4 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-colors">
      <div className="flex gap-4">
        <div className={`mt-1 ${colorClass}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="font-bold text-sm text-white">{label}</div>
          <div className="text-xs text-zinc-500 mt-1 max-w-md">{desc}</div>
        </div>
      </div>
      <button 
        onClick={onChange}
        className={`w-12 h-6 rounded-full transition-colors relative shrink-0 ${checked ? "bg-cyan-500" : "bg-zinc-700"}`}
      >
        <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${checked ? "left-7" : "left-1"}`} />
      </button>
    </div>
  );

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h2 className="text-xl font-black uppercase tracking-widest text-white mb-2">Notifications</h2>
        <p className="text-sm text-zinc-500">Control when and how Nexus contacts you.</p>
      </div>

      <div className="space-y-4">
        <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-600 mb-4 px-2">System Alerts</h3>
        
        <Toggle 
          icon={Bell} colorClass="text-cyan-400"
          label="Session Completion" 
          desc="Receive an email summary and transcript link when an autonomous session finishes successfully."
          checked={prefs.sessionEnd}
          onChange={() => setPrefs({...prefs, sessionEnd: !prefs.sessionEnd})}
        />
        
        <Toggle 
          icon={AlertTriangle} colorClass="text-amber-400"
          label="Critical Errors" 
          desc="Get notified immediately if a session crashes or encounters an unrecoverable sandbox state."
          checked={prefs.errors}
          onChange={() => setPrefs({...prefs, errors: !prefs.errors})}
        />

        <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-600 mb-4 px-2 mt-8">Digests</h3>

        <Toggle 
          icon={Mail} colorClass="text-emerald-400"
          label="Weekly Analytics Digest" 
          desc="A Sunday email summarizing your total uptime, messages, and command breakdown."
          checked={prefs.weeklyDigest}
          onChange={() => setPrefs({...prefs, weeklyDigest: !prefs.weeklyDigest})}
        />
      </div>

      <div className="pt-6 border-t border-white/5">
        <button 
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 text-black font-black text-xs uppercase tracking-widest hover:bg-cyan-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : "Save Preferences"}
        </button>
      </div>
    </div>
  );
}
