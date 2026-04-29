"use client";

import { useAuth } from "@/lib/auth-context";
import { Volume2, Save, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { fetchUserSettings, updateUserSettings } from "@/lib/user-settings";

const VOICES = [
  { id: "Puck", name: "Puck", desc: "Warm, natural, clear", gender: "Male" },
  { id: "Charon", name: "Charon", desc: "Authoritative, deep", gender: "Male" },
  { id: "Kore", name: "Kore", desc: "Friendly, dynamic", gender: "Female" },
  { id: "Fenrir", name: "Fenrir", desc: "Fast, energetic", gender: "Male" },
  { id: "Aoede", name: "Aoede", desc: "Soft, empathetic", gender: "Female" },
];

export default function VoiceSettingsPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [voiceId, setVoiceId] = useState("Puck");
  const [ttsSpeed, setTtsSpeed] = useState(1.0);

  useEffect(() => {
    let cancelled = false;

    async function loadSettings() {
      if (!user) {
        setLoading(false);
        return;
      }

      try {
        const response = await fetchUserSettings();
        if (cancelled) {
          return;
        }

        const voiceSettings =
          response.settings.voice &&
          typeof response.settings.voice === "object" &&
          !Array.isArray(response.settings.voice)
            ? (response.settings.voice as { voiceId?: string; speed?: number })
            : null;

        setVoiceId(voiceSettings?.voiceId || "Puck");
        setTtsSpeed(
          typeof voiceSettings?.speed === "number" ? voiceSettings.speed : 1.0,
        );
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load voice settings:", err);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSettings();

    return () => {
      cancelled = true;
    };
  }, [user]);

  const handleSave = async () => {
    if (!user) return;
    setSaving(true);
    try {
      await updateUserSettings({
        settings: {
          voice: {
            voiceId,
            speed: ttsSpeed,
          },
        },
      });
    } catch (err) {
      console.error("Failed to save voice settings:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl text-zinc-900 dark:text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 mb-2">Voice & Audio</h2>
        <p className="text-sm text-zinc-500">Configure how CoComputer sounds and processes your speech.</p>
      </div>

      <div className="space-y-6">
        <section className="p-6 rounded-3xl bg-white dark:bg-[#1a1a1c] border border-zinc-200 dark:border-[#2f2f35]">
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-zinc-500" />
            Synthesis Model
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
            {VOICES.map(v => {
              const isSelected = v.id === voiceId;
              return (
                <button
                  key={v.id}
                  onClick={() => setVoiceId(v.id)}
                  className={`flex items-center justify-between p-4 rounded-3xl border text-left transition-all ${
                    isSelected 
                      ? "border-zinc-900 bg-zinc-50 dark:border-zinc-100 dark:bg-zinc-800/50" 
                      : "border-zinc-200 bg-white hover:bg-zinc-50 dark:border-[#2f2f35] dark:bg-[#1a1a1c] dark:hover:bg-zinc-800/30"
                  }`}
                >
                  <div>
                    <div className={`font-medium text-sm ${isSelected ? "text-zinc-900 dark:text-zinc-100" : "text-zinc-700 dark:text-zinc-300"}`}>
                      {v.name}
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">{v.desc}</div>
                  </div>
                  {isSelected && (
                    <div className="w-2 h-2 rounded-full bg-zinc-900 dark:bg-zinc-100 shadow-sm" />
                  )}
                </button>
              );
            })}
          </div>

          <div className="space-y-4 pt-6 border-t border-zinc-200 dark:border-zinc-800">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Speaking Rate</label>
              <span className="text-xs font-mono text-zinc-500 bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded-md">{ttsSpeed.toFixed(1)}x</span>
            </div>
            <input
              type="range"
              min="0.5" max="2.0" step="0.1"
              value={ttsSpeed}
              onChange={(e) => setTtsSpeed(parseFloat(e.target.value))}
              className="w-full accent-zinc-900 dark:accent-zinc-100"
            />
            <div className="flex justify-between text-xs text-zinc-500">
              <span>Slower</span>
              <span>Faster</span>
            </div>
          </div>
        </section>

      </div>

      <div className="pt-6 border-t border-zinc-200 dark:border-[#2f2f35]">
        <button
          onClick={handleSave}
          disabled={saving || loading || !user}
          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-full bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 font-medium text-sm transition-colors hover:bg-zinc-800 dark:hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed w-full sm:w-auto"
        >
          {saving || loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {loading ? "Loading..." : saving ? "Saving..." : "Save Configuration"}
        </button>
      </div>
    </div>
  );
}
