"use client";

import { useState } from "react";
import { Save, Loader2, Mic, Volume2 } from "lucide-react";
import { getAuth } from "firebase/auth";

export default function VoiceSettingsPage() {
  const [saving, setSaving] = useState(false);
  const [voiceId, setVoiceId] = useState("Calm_Woman");
  const [speed, setSpeed] = useState(1.0);
  const [autoMic, setAutoMic] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const token = await getAuth().currentUser?.getIdToken();
      await fetch("http://localhost:8000/api/v1/user/settings", {
        method: "PATCH",
        headers: { 
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ "settings.voiceId": voiceId, "settings.voiceSpeed": speed, "settings.autoMic": autoMic })
      });
      alert("Voice settings updated successfully");
    } catch (e) {
      alert("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h2 className="text-xl font-black uppercase tracking-widest text-white mb-2">Voice & AI</h2>
        <p className="text-sm text-zinc-500">Configure the neural synthesis and interaction model.</p>
      </div>

      <div className="space-y-6">
        <div className="space-y-3">
          <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 flex items-center gap-2">
            <Mic className="w-3 h-3" /> Synthesis Model
          </label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {["Calm_Woman", "Authoritative_Male", "Neutral_Assist", "Dynamic_Guide"].map(vid => (
              <button
                key={vid}
                onClick={() => setVoiceId(vid)}
                className={`flex items-center justify-between p-4 rounded-xl border text-left transition-all ${
                  voiceId === vid 
                    ? "bg-cyan-500/10 border-cyan-500 shadow-[0_0_15px_rgba(34,211,238,0.2)]" 
                    : "bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20"
                }`}
              >
                <div>
                  <div className={`font-bold text-sm ${voiceId === vid ? "text-cyan-400" : "text-white"}`}>
                    {vid.replace("_", " ")}
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">MiniMax Kilo Engine</div>
                </div>
                {voiceId === vid && <div className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 flex items-center gap-2">
            <Volume2 className="w-3 h-3" /> Output Speed: {speed.toFixed(1)}x
          </label>
          <input 
            type="range" 
            min="0.5" max="2.0" step="0.1"
            value={speed}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
            className="w-full accent-cyan-500"
          />
          <div className="flex justify-between text-xs font-mono text-zinc-600">
            <span>Slow (0.5x)</span>
            <span>Normal (1.0x)</span>
            <span>Fast (2.0x)</span>
          </div>
        </div>

        <div className="pt-4 flex items-center justify-between p-4 rounded-xl bg-white/5 border border-white/10">
          <div>
            <div className="font-bold text-sm text-white">Auto-start Microphone</div>
            <div className="text-xs text-zinc-500 mt-1">Activate mic immediately when session starts</div>
          </div>
          <button 
            onClick={() => setAutoMic(!autoMic)}
            className={`w-12 h-6 rounded-full transition-colors relative ${autoMic ? "bg-cyan-500" : "bg-zinc-700"}`}
          >
            <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${autoMic ? "left-7" : "left-1"}`} />
          </button>
        </div>
      </div>

      <div className="pt-6 border-t border-white/5">
        <button 
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 text-black font-black text-xs uppercase tracking-widest hover:bg-cyan-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Deploying..." : "Apply Configuration"}
        </button>
      </div>
    </div>
  );
}
