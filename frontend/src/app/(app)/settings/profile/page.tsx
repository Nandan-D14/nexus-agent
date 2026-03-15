"use client";

import { useAuth } from "@/lib/auth-context";
import { useState, useEffect } from "react";
import { Save, Loader2, Camera, Moon, Sun, Monitor, HardDrive, Link, Unlink } from "lucide-react";
import { authenticatedFetch } from "@/lib/api-client";
import { useToast } from "@/components/toast-provider";
import { useTheme } from "next-themes";

export default function ProfileSettingsPage() {
  const { user } = useAuth();
  const { toast } = useToast();
  const { theme, setTheme } = useTheme();

  const [mounted, setMounted] = useState(false);
  const [saving, setSaving] = useState(false);

  // Google Drive state
  const [gdriveConnected, setGdriveConnected] = useState(false);
  const [gdriveLoading, setGdriveLoading] = useState(false);
  const [gdriveSupported, setGdriveSupported] = useState(false);

  const [displayName, setDisplayName] = useState(user?.displayName || "");
  const [bio, setBio] = useState("");
  const [avatarUrl, setAvatarUrl] = useState(user?.photoURL || "");

  useEffect(() => {
    setMounted(true);
    // Load user settings to check Google Drive status
    authenticatedFetch("/api/v1/user/settings")
      .then((r) => r.json())
      .then((data: Record<string, unknown>) => {
        setGdriveConnected(!!data?.googleDriveRefreshToken);
      })
      .catch(() => {});
    // Check if Google Drive OAuth is configured on the backend
    authenticatedFetch("/api/v1/auth/google-drive/url")
      .then(() => setGdriveSupported(true))
      .catch(() => {
        // 501 = not configured; we still mark as unsupported
        setGdriveSupported(false);
      });
  }, []);

  // Listen for OAuth popup success
  useEffect(() => {
    const handler = (evt: MessageEvent) => {
      if (evt.origin !== window.location.origin) return;
      if ((evt.data as { type?: string })?.type === "google_drive_connected") {
        setGdriveConnected(true);
        toast("Google Drive connected!", "success");
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [toast]);

  const handleConnectGDrive = async () => {
    setGdriveLoading(true);
    try {
      const data = (await authenticatedFetch("/api/v1/auth/google-drive/url").then((r) => r.json())) as {
        auth_url: string;
      };
      const popup = window.open(
        data.auth_url,
        "Google Drive Authorization",
        "width=550,height=650,scrollbars=yes,resizable=yes"
      );
      if (!popup) toast("Pop-up blocked. Please allow pop-ups for this page.", "error");
    } catch {
      toast("Failed to start Google Drive authorization.", "error");
    } finally {
      setGdriveLoading(false);
    }
  };

  const handleDisconnectGDrive = async () => {
    setGdriveLoading(true);
    try {
      await authenticatedFetch("/api/v1/auth/google-drive", { method: "DELETE" });
      setGdriveConnected(false);
      toast("Google Drive disconnected.", "success");
    } catch {
      toast("Failed to disconnect Google Drive.", "error");
    } finally {
      setGdriveLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => setAvatarUrl(evt.target?.result as string);
    reader.readAsDataURL(file);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await authenticatedFetch("/api/v1/user/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ displayName, bio, avatarUrl }),
      });
      toast("Profile updated successfully", "success");
    } catch {
      toast("Failed to save profile", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl text-zinc-900 dark:text-zinc-100">
      <div>
        <h2 className="text-xl font-black uppercase tracking-widest text-zinc-900 dark:text-white mb-2">Public Profile</h2>
        <p className="text-sm text-zinc-500">Your information visible to the network.</p>
      </div>

      <div className="flex items-center gap-6 pb-6 border-b border-zinc-200 dark:border-white/10">
        <label className="relative group cursor-pointer block">
          <input type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
          {avatarUrl ? (
            <img src={avatarUrl} alt="Avatar" className="w-24 h-24 rounded-full border border-black/10 dark:border-white/10 object-cover" />
          ) : (
            <div className="w-24 h-24 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center border border-black/10 dark:border-white/10">
              <span className="text-4xl text-zinc-500 font-bold">{user?.email?.[0].toUpperCase()}</span>
            </div>
          )}
          <div className="absolute inset-0 bg-black/60 rounded-full opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <Camera className="w-6 h-6 text-white" />
          </div>
        </label>
        <div>
          <h3 className="font-bold text-zinc-900 dark:text-white">{user?.email}</h3>
          <p className="text-xs text-zinc-500 mt-1 uppercase tracking-widest font-mono">UID: {user?.uid.slice(0, 8)}...</p>
        </div>
      </div>

      <div className="space-y-6">
        <div className="space-y-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">Display Name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full bg-zinc-100 dark:bg-white/5 border border-zinc-200 dark:border-white/10 rounded-xl px-4 py-3 placeholder:text-zinc-400 dark:text-white dark:focus:border-cyan-500/50 focus:border-cyan-600 focus:outline-none transition-colors"
            placeholder="Agent Name"
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">Bio / Designation</label>
          <textarea
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            rows={4}
            className="w-full bg-zinc-100 dark:bg-white/5 border border-zinc-200 dark:border-white/10 rounded-xl px-4 py-3 placeholder:text-zinc-400 dark:text-white dark:focus:border-cyan-500/50 focus:border-cyan-600 focus:outline-none transition-colors resize-none"
            placeholder="System operations expert..."
          />
        </div>

        {mounted && (
          <div className="space-y-3 pt-4 border-t border-zinc-200 dark:border-white/10">
            <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400 block mb-2">Theme Preference</label>
            <div className="flex bg-zinc-200 dark:bg-zinc-900/50 p-1 rounded-2xl w-fit">
              <button
                onClick={() => setTheme("light")}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  theme === "light"
                    ? "bg-white text-cyan-600 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300"
                }`}
              >
                <Sun className="w-4 h-4" />
                Light
              </button>
              <button
                onClick={() => setTheme("dark")}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  theme === "dark"
                    ? "bg-zinc-800 text-cyan-400 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300"
                }`}
              >
                <Moon className="w-4 h-4" />
                Dark
              </button>
              <button
                onClick={() => setTheme("system")}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  theme === "system"
                    ? "bg-white dark:bg-zinc-800 text-cyan-600 dark:text-cyan-400 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300"
                }`}
              >
                <Monitor className="w-4 h-4" />
                System
              </button>
            </div>
          </div>
        )}

        {/* Google Drive Integration */}
        <div className="space-y-3 pt-4 border-t border-zinc-200 dark:border-white/10">
          <div className="flex items-center gap-2 mb-1">
            <HardDrive className="w-4 h-4 text-zinc-500" />
            <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">Google Drive</label>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-600">
            Mount your Google Drive at <code className="font-mono text-cyan-600 dark:text-cyan-400">~/gdrive</code> in every sandbox session.
          </p>

          {gdriveConnected ? (
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-xs text-emerald-500 font-bold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                Connected
              </span>
              <button
                onClick={handleDisconnectGDrive}
                disabled={gdriveLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 text-xs font-bold uppercase tracking-widest text-zinc-600 dark:text-zinc-400 hover:border-red-500 hover:text-red-500 transition-all disabled:opacity-50"
              >
                {gdriveLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Unlink className="w-3 h-3" />}
                Disconnect
              </button>
            </div>
          ) : (
            <button
              onClick={handleConnectGDrive}
              disabled={gdriveLoading || !gdriveSupported}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-zinc-100 dark:bg-white/5 border border-zinc-200 dark:border-white/10 text-xs font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300 hover:border-cyan-500 hover:text-cyan-600 dark:hover:text-cyan-400 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {gdriveLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Link className="w-3 h-3" />}
              {gdriveSupported ? "Connect Google Drive" : "Not configured"}
            </button>
          )}
        </div>
      </div>

      <div className="pt-6">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-600 dark:bg-cyan-500 text-white dark:text-black font-black text-xs uppercase tracking-widest hover:bg-cyan-500 dark:hover:bg-cyan-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
}
