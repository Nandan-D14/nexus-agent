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
    <div className="flex items-start justify-between p-4 rounded-3xl bg-white dark:bg-[#111114] border border-zinc-200 dark:border-[#2f2f35] transition-colors">
      <div className="flex gap-4">
        <div className={`mt-1 ${colorClass}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="font-medium text-sm text-zinc-900 dark:text-zinc-100">{label}</div>
          <div className="text-xs text-zinc-500 mt-1 max-w-md">{desc}</div>
        </div>
      </div>
      <button
        onClick={onChange}
        className={`w-11 h-6 rounded-full transition-colors relative shrink-0 ${checked ? "bg-zinc-900 dark:bg-zinc-100" : "bg-zinc-200 dark:bg-zinc-800"}`}
      >
        <div className={`absolute top-1 w-4 h-4 rounded-full bg-white dark:bg-[#111114] shadow-sm transition-all ${checked ? "left-6" : "left-1"}`} />
      </button>
    </div>
  );

  return (
    <div className="space-y-8 max-w-2xl text-zinc-900 dark:text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 mb-2">Notifications</h2>
        <p className="text-sm text-zinc-500">Control when and how Nexus contacts you.</p>
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 px-2">System Alerts</h3>
        
        <Toggle
          icon={Bell} colorClass="text-emerald-600 dark:text-emerald-500"
          label="Session Completion"
          desc="Receive an email summary and transcript link when an autonomous session finishes successfully."
          checked={prefs.sessionEnd}
          onChange={() => setPrefs({...prefs, sessionEnd: !prefs.sessionEnd})}
        />

        <Toggle
          icon={AlertTriangle} colorClass="text-amber-600 dark:text-amber-500"
          label="Critical Errors"
          desc="Get notified immediately if a session crashes or encounters an unrecoverable sandbox state."
          checked={prefs.errors}
          onChange={() => setPrefs({...prefs, errors: !prefs.errors})}
        />

        <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 px-2 mt-8">Digests</h3>
        <Toggle
          icon={Mail} colorClass="text-cyan-600 dark:text-cyan-500"
          label="Weekly Analytics Digest"
          desc="A Sunday email summarizing your total uptime, messages, and command breakdown."
          checked={prefs.weeklyDigest}
          onChange={() => setPrefs({...prefs, weeklyDigest: !prefs.weeklyDigest})}
        />
      </div>

      <div className="pt-6 border-t border-zinc-200 dark:border-[#2f2f35]">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-full bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 font-medium text-sm transition-colors hover:bg-zinc-800 dark:hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : "Save Preferences"}
        </button>
      </div>
    </div>
  );
}
