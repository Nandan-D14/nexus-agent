"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  KeyRound,
  User,
  Mic,
  Bell,
  Loader2,
  Save,
  AlertCircle,
  CheckCircle2,
  Server,
  Monitor,
  Sun,
  Moon,
  Volume2,
  AlertTriangle,
  Mail,
  Lock,
  ChevronRight,
  Settings2,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useTheme } from "next-themes";
import { useToast } from "@/components/toast-provider";
import { useSettings } from "@/lib/settings-context";
import {
  type GeminiProvider,
  type UserSettingsResponse,
  fetchUserSettings,
  updateUserSettings,
} from "@/lib/user-settings";

/* ------------------------------------------------------------------ */
/*  Types                                                               */
/* ------------------------------------------------------------------ */

type TabId = "api" | "profile" | "voice" | "notifications";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: TabId;
};

/* ------------------------------------------------------------------ */
/*  Sub-components                                                       */
/* ------------------------------------------------------------------ */

function TabButton({ 
  active, 
  onClick, 
  icon: Icon, 
  label 
}: { 
  active: boolean; 
  onClick: () => void; 
  icon: any; 
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-200 text-left w-full ${
        active
          ? "bg-zinc-800 dark:bg-muted text-white dark:text-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-zinc-800/40 dark:hover:bg-muted/40"
      }`}
    >
      <Icon className={`w-4 h-4 ${active ? "text-white dark:text-foreground" : "text-muted-foreground"}`} />
      <span className="text-[13px] font-medium">{label}</span>
    </button>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      <div className="space-y-4">
        {children}
      </div>
    </div>
  );
}

/* ── API & Keys Tab ── */
function ApiTab({ settings, onUpdate }: { settings: UserSettingsResponse | null; onUpdate: (data: UserSettingsResponse) => void }) {
  const { toast } = useToast();
  const { refreshBetaStatus } = useSettings();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accessCode, setAccessCode] = useState("");
  const [e2bApiKey, setE2bApiKey] = useState("");
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [geminiProvider, setGeminiProvider] = useState<GeminiProvider>(settings?.byok.geminiProvider || "apiKey");

  const sharedE2bReady = Boolean(settings?.byok.sharedAccessEnabled && settings.byok.serverE2bConfigured);
  const sharedVertexReady = Boolean(settings?.byok.sharedAccessEnabled && settings.byok.vertexConfigured);
  const e2bReady = Boolean(settings?.byok.e2bKeySet || sharedE2bReady);
  const geminiReady = Boolean(settings && (geminiProvider === "vertex" ? sharedVertexReady : settings.byok.geminiKeySet));

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const payload: any = { byok: { geminiProvider } };
      if (e2bApiKey.trim()) payload.byok.e2bApiKey = e2bApiKey.trim();
      if (geminiProvider === "apiKey" && geminiApiKey.trim()) payload.byok.geminiApiKey = geminiApiKey.trim();
      if (accessCode.trim()) payload.byok.accessCode = accessCode.trim();

      const updated = await updateUserSettings(payload);
      onUpdate(updated);
      setAccessCode(""); setE2bApiKey(""); setGeminiApiKey("");
      toast("Settings saved successfully.", "success");
      
      // Refresh beta status to update requiresByokSetup globally
      void refreshBetaStatus();
    } catch (err: any) {
      setError(err.message || "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-10">
      <Section title="API Access" description="Connect external services to power agent execution.">
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
            {error}
          </div>
        )}

        {settings?.byok.sharedAccessCodeConfigured && (
          <div className="space-y-2">
             <label className="text-[11px] font-bold text-muted-foreground uppercase">Shared Access Code</label>
             <input
               type="password"
               value={accessCode}
               onChange={(e) => setAccessCode(e.target.value)}
               placeholder="Enter access code"
               className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-600 transition-colors"
             />
          </div>
        )}

        <div className="space-y-2">
           <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold text-muted-foreground uppercase">E2B API Key</label>
              {e2bReady && <span className="text-[10px] text-emerald-500 font-medium flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Ready</span>}
           </div>
           <input
             type="password"
             value={e2bApiKey}
             onChange={(e) => setE2bApiKey(e.target.value)}
             placeholder={settings?.byok.e2bKeySet ? "••••••••••••••••" : "Enter E2B key"}
             className="w-full bg-input-bg border border-input-border rounded-lg px-4 py-2 text-sm text-foreground outline-none focus:border-zinc-600 transition-colors"
           />
        </div>

        <div className="space-y-4 pt-2">
           <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold text-muted-foreground uppercase">Gemini Configuration</label>
              {geminiReady && <span className="text-[10px] text-emerald-500 font-medium flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Configured</span>}
           </div>
           
           <div className="flex gap-2">
             {["apiKey", "vertex"].map((p) => (
               <button
                 key={p}
                 onClick={() => setGeminiProvider(p as GeminiProvider)}
                 className={`flex-1 py-2 rounded-lg border text-xs font-medium transition-all ${geminiProvider === p ? "bg-white text-black border-white" : "bg-transparent text-muted-foreground border-zinc-800 hover:text-foreground"}`}
               >
                 {p === "apiKey" ? "Direct API Key" : "Google Vertex AI"}
               </button>
             ))}
           </div>

           {geminiProvider === "apiKey" && (
             <input
               type="password"
               value={geminiApiKey}
               onChange={(e) => setGeminiApiKey(e.target.value)}
               placeholder={settings?.byok.geminiKeySet ? "••••••••••••••••" : "Enter Gemini API Key"}
               className="w-full bg-input-bg border border-input-border rounded-lg px-4 py-2 text-sm text-foreground outline-none focus:border-zinc-600 transition-colors"
             />
           )}
        </div>
      </Section>

      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full bg-white hover:bg-zinc-200 text-black font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 text-sm"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        Save API Settings
      </button>
    </div>
  );
}

/* ── Profile Tab ── */
function ProfileTab() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();

  return (
    <div className="space-y-10">
      <Section title="Profile" description="Your personal account information.">
        <div className="flex items-center gap-4 py-2">
          <div className="w-12 h-12 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center overflow-hidden">
            {user?.photoURL ? <img src={user.photoURL} alt="" className="w-full h-full object-cover" /> : <User className="w-6 h-6 text-zinc-600" />}
          </div>
          <div>
            <div className="text-sm font-semibold text-foreground">{user?.displayName || "Operator"}</div>
            <div className="text-xs text-muted-foreground">{user?.email}</div>
          </div>
        </div>
      </Section>

      <Section title="Appearance" description="Customize how the application looks.">
        <div className="grid grid-cols-3 gap-2">
          {[
            { id: "light", icon: Sun, label: "Light" },
            { id: "dark", icon: Moon, label: "Dark" },
            { id: "system", icon: Monitor, label: "System" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTheme(t.id)}
              className={`flex items-center justify-center gap-2 py-2 rounded-lg border text-xs font-medium transition-all ${theme === t.id ? "bg-zinc-800 text-white border-zinc-700" : "bg-transparent text-muted-foreground border-zinc-800 hover:text-foreground"}`}
            >
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>
      </Section>
    </div>
  );
}

/* ── Voice Tab ── */
const VOICES = [
  { id: "Puck", name: "Puck" },
  { id: "Charon", name: "Charon" },
  { id: "Kore", name: "Kore" },
  { id: "Fenrir", name: "Fenrir" },
];

function VoiceTab({ settings, onUpdate }: { settings: UserSettingsResponse | null; onUpdate: (data: UserSettingsResponse) => void }) {
  const [saving, setSaving] = useState(false);
  const voiceSettings = useMemo(() => (settings?.settings.voice as { voiceId?: string; speed?: number }) || {}, [settings]);
  const [voiceId, setVoiceId] = useState(voiceSettings.voiceId || "Puck");
  const [speed, setSpeed] = useState(voiceSettings.speed || 1.0);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateUserSettings({ settings: { voice: { voiceId, speed } } });
      onUpdate(updated);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-10">
      <Section title="Voice Settings" description="Configure the agent's interaction voice.">
        <div className="grid grid-cols-2 gap-2">
          {VOICES.map((v) => (
            <button
              key={v.id}
              onClick={() => setVoiceId(v.id)}
              className={`px-4 py-2.5 rounded-lg border text-sm font-medium transition-all text-left ${voiceId === v.id ? "bg-zinc-800 text-white border-zinc-700" : "bg-transparent text-muted-foreground border-zinc-800 hover:border-zinc-700"}`}
            >
              {v.name}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Speaking Rate" description="Adjust the playback speed of the agent's voice.">
        <div className="space-y-4 py-2">
          <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>Slow</span>
            <span className="text-foreground">{speed.toFixed(1)}x</span>
            <span>Fast</span>
          </div>
          <input
            type="range" min="0.5" max="2.0" step="0.1" value={speed}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
            className="w-full accent-white h-1 bg-zinc-800 rounded-full appearance-none cursor-pointer"
          />
        </div>
      </Section>

      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full bg-white hover:bg-zinc-200 text-black font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 text-sm"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        Save Voice Settings
      </button>
    </div>
  );
}

/* ── Notifications Tab ── */
function NotificationsTab() {
  const [saving, setSaving] = useState(false);
  const [prefs, setPrefs] = useState({ sessionEnd: true, errors: true, weekly: false });

  return (
    <div className="space-y-10">
      <Section title="Notifications" description="Choose which alerts you want to receive.">
        <div className="space-y-2">
          {[
            { id: "sessionEnd", label: "Session completion alerts" },
            { id: "errors", label: "Critical error reports" },
            { id: "weekly", label: "Weekly activity digests" },
          ].map((p) => (
            <button
              key={p.id}
              onClick={() => setPrefs({ ...prefs, [p.id]: !((prefs as any)[p.id]) })}
              className="w-full flex items-center justify-between p-4 rounded-lg border border-zinc-800 bg-zinc-900/20 hover:bg-zinc-900/40 transition-all"
            >
              <span className="text-sm font-medium text-foreground">{p.label}</span>
              <div className={`w-8 h-4 rounded-full relative transition-colors ${((prefs as any)[p.id]) ? "bg-white" : "bg-zinc-800"}`}>
                <div className={`absolute top-0.5 w-3 h-3 rounded-full transition-all ${((prefs as any)[p.id]) ? "bg-black left-4.5" : "bg-zinc-500 left-0.5"}`} />
              </div>
            </button>
          ))}
        </div>
      </Section>

      <button
        onClick={() => { setSaving(true); setTimeout(() => setSaving(false), 800); }}
        disabled={saving}
        className="w-full bg-white hover:bg-zinc-200 text-black font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 text-sm"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        Save Preferences
      </button>
    </div>
  );
}

/* ── Main Modal Component ── */
export function SettingsModal({ isOpen, onClose, initialTab = "api" }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [settings, setSettings] = useState<UserSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    fetchUserSettings().then(setSettings).finally(() => setLoading(false));
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
      />

      <motion.div
        initial={{ opacity: 0, scale: 0.99 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.99 }}
        className="relative w-full max-w-4xl h-[700px] bg-card border border-card-border rounded-xl shadow-2xl overflow-hidden flex flex-col md:flex-row"
      >
        {/* Sidebar */}
        <div className="w-full md:w-60 border-b md:border-b-0 md:border-r border-zinc-800/60 bg-card p-6 flex flex-col shrink-0">
          <div className="flex items-center gap-2 font-bold text-foreground mb-8 px-1">
            <Settings2 className="w-5 h-5" />
            <span className="text-sm font-semibold">Settings</span>
          </div>

          <nav className="space-y-1">
            <TabButton label="API Settings" icon={KeyRound} active={activeTab === "api"} onClick={() => setActiveTab("api")} />
            <TabButton label="Profile" icon={User} active={activeTab === "profile"} onClick={() => setActiveTab("profile")} />
            <TabButton label="Voice" icon={Mic} active={activeTab === "voice"} onClick={() => setActiveTab("voice")} />
            <TabButton label="Notifications" icon={Bell} active={activeTab === "notifications"} onClick={() => setActiveTab("notifications")} />
          </nav>
        </div>

        {/* Content Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-card">
          <div className="h-14 border-b border-zinc-800/40 flex items-center justify-between px-8">
             <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{activeTab}</span>
             <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors p-1">
               <X className="w-4 h-4" />
             </button>
          </div>

          <div className="flex-1 overflow-y-auto p-10 custom-scrollbar">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="max-w-xl">
                {activeTab === "api" && <ApiTab settings={settings} onUpdate={setSettings} />}
                {activeTab === "profile" && <ProfileTab />}
                {activeTab === "voice" && <VoiceTab settings={settings} onUpdate={setSettings} />}
                {activeTab === "notifications" && <NotificationsTab />}
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
