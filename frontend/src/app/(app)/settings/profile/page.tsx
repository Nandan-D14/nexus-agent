"use client";

import { useAuth } from "@/lib/auth-context";
import { Mail, Shield, User as UserIcon, Monitor, Moon, Sun, Cloud, HardDrive, Key } from "lucide-react";
import { useState, useEffect } from "react";
import { useTheme } from "next-themes";
import Link from 'next/link';
import { db } from "@/lib/firebase-client";
import { doc, getDoc, setDoc } from "firebase/firestore";

interface DrivePrefs {
  autoExportDocs: boolean;
  exportFormat: "markdown" | "html" | "plain";
  includeAudio: boolean;
}

export default function ProfileSettingsPage() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [loadingDrive, setLoadingDrive] = useState(false);
  
  // Google Drive state
  const [driveConnected, setDriveConnected] = useState(false);
  const [drivePrefs, setDrivePrefs] = useState<DrivePrefs>({
    autoExportDocs: true,
    exportFormat: "markdown",
    includeAudio: false
  });

  useEffect(() => {
    setMounted(true);
    checkDriveStatus();
  }, [user]);

  const checkDriveStatus = async () => {
    if (!user) return;
    try {
      const docSnap = await getDoc(doc(db, "users", user.uid));
      if (docSnap.exists()) {
        const data = docSnap.data();
        if (data.googleDriveTokens) {
          setDriveConnected(true);
        }
        if (data.drivePrefs) {
          setDrivePrefs({ ...drivePrefs, ...data.drivePrefs });
        }
      }
    } catch (err) {
      console.error("Failed to check Drive status:", err);
    }
  };

  const handleConnectDrive = () => {
    if (!user) return;
    window.location.href = `/api/auth/google-drive/init?uid=${user.uid}`;
  };

  const handleDisconnectDrive = async () => {
    if (!user || !confirm("Disconnect Google Drive? Features relying on Drive will stop working.")) return;
    
    setLoadingDrive(true);
    try {
      await setDoc(doc(db, "users", user.uid), {
        googleDriveTokens: null
      }, { merge: true });
      setDriveConnected(false);
    } catch (err) {
      console.error("Failed to disconnect Drive:", err);
      alert("Failed to disconnect Drive");
    } finally {
      setLoadingDrive(false);
    }
  };

  if (!mounted) return null;

  return (
    <div className="space-y-8 max-w-2xl text-zinc-900 dark:text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 mb-2">Account</h2>
        <p className="text-sm text-zinc-500">Manage your user profile and workspace preferences.</p>
      </div>

      <div className="space-y-6">
        <section className="p-6 rounded-3xl bg-white dark:bg-[#111114] border border-zinc-200 dark:border-[#2f2f35]">
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 flex items-center gap-2">
            <Mail className="w-4 h-4 text-zinc-500" />
            Contact Email
          </h3>
          <div className="flex items-center gap-3 w-full bg-zinc-50 dark:bg-zinc-800/50 p-3 rounded-full border border-zinc-200 dark:border-zinc-800">
             <div className="text-sm text-zinc-500 font-mono px-2">{user?.email || "Not signed in"}</div>
          </div>
          <p className="text-xs text-zinc-500 mt-2 px-2">This email is used for authentication and communications.</p>
        </section>


        {/* Appearance Settings */}
        <section className="p-6 rounded-3xl bg-white dark:bg-[#111114] border border-zinc-200 dark:border-[#2f2f35]">
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 flex items-center gap-2">
            <Monitor className="w-4 h-4 text-zinc-500" />
            Theme Preferences
          </h3>
          
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={() => setTheme("light")}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all ${
                theme === "light" 
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" 
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              }`}
            >
              <Sun className="w-4 h-4" />
              Light
            </button>
            <button
              onClick={() => setTheme("dark")}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all ${
                theme === "dark" 
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" 
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              }`}
            >
              <Moon className="w-4 h-4" />
              Dark
            </button>
            <button
              onClick={() => setTheme("system")}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all ${
                theme === "system" 
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" 
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              }`}
            >
              <Monitor className="w-4 h-4" />
              System
            </button>
          </div>
        </section>

        {/* Google Drive Integration */}
        <section className="p-6 rounded-3xl bg-white dark:bg-[#111114] border border-zinc-200 dark:border-[#2f2f35]">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
              <Cloud className="w-4 h-4 text-emerald-500" />
              Google Drive Cloud
            </h3>
            {driveConnected ? (
              <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-500 text-xs font-medium border border-emerald-500/20">
                Connected
              </span>
            ) : null}
          </div>
          
          <p className="text-sm text-zinc-500 mb-6">
            Connect your Google Drive to allow Nexus to read documents, create spreadsheets, and continuously auto-export session transcripts.
          </p>

          {!driveConnected ? (
            <button
              onClick={handleConnectDrive}
              className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 font-medium text-sm transition-all hover:opacity-90"
            >
              <HardDrive className="w-4 h-4" />
              Connect Google Drive via OAuth
            </button>
          ) : (
            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/30 border border-zinc-200 dark:border-zinc-800">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Storage Authorized</h4>
                    <p className="text-xs text-zinc-500 mt-1">Nexus has secure, sandboxed access to manage files.</p>
                  </div>
                  <button
                    onClick={handleDisconnectDrive}
                    disabled={loadingDrive}
                    className="px-4 py-2 rounded-full border border-red-500/20 text-red-500 text-sm font-medium hover:bg-red-500/10 transition-colors disabled:opacity-50"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
