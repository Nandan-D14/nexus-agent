"use client";

import { useAuth } from "@/lib/auth-context";
import { useState } from "react";
import { Save, Loader2, Camera } from "lucide-react";
import { getAuth } from "firebase/auth";
import { useToast } from "@/components/toast-provider";

export default function ProfileSettingsPage() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  
  // Future: Initialize from backend GET /api/v1/user/settings
  const [displayName, setDisplayName] = useState(user?.displayName || "");
  const [bio, setBio] = useState("");
  const [avatarUrl, setAvatarUrl] = useState(user?.photoURL || "");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      setAvatarUrl(evt.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

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
        body: JSON.stringify({ displayName, bio, avatarUrl })
      });
      toast("Profile updated successfully", "success");
    } catch (e) {
      toast("Failed to save profile", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h2 className="text-xl font-black uppercase tracking-widest text-white mb-2">Public Profile</h2>
        <p className="text-sm text-zinc-500">Your information visible to the network.</p>
      </div>

      <div className="flex items-center gap-6 pb-6 border-b border-white/10">
        <label className="relative group cursor-pointer block">
          <input type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
          {avatarUrl ? (
            <img src={avatarUrl} alt="Avatar" className="w-24 h-24 rounded-full border border-white/10 object-cover" />
          ) : (
            <div className="w-24 h-24 rounded-full bg-zinc-800 flex items-center justify-center border border-white/10">
              <span className="text-4xl text-zinc-500 font-bold">{user?.email?.[0].toUpperCase()}</span>
            </div>
          )}
          <div className="absolute inset-0 bg-black/60 rounded-full opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <Camera className="w-6 h-6 text-white" />
          </div>
        </label>
        <div>
          <h3 className="text-white font-bold">{user?.email}</h3>
          <p className="text-xs text-zinc-500 mt-1 uppercase tracking-widest font-mono">UID: {user?.uid.slice(0, 8)}...</p>
        </div>
      </div>

      <div className="space-y-6">
        <div className="space-y-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Display Name</label>
          <input 
            type="text" 
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 transition-colors"
            placeholder="Agent Name"
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Bio / Designation</label>
          <textarea 
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            rows={4}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 transition-colors resize-none"
            placeholder="System operations expert..."
          />
        </div>
      </div>

      <div className="pt-6">
        <button 
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 text-black font-black text-xs uppercase tracking-widest hover:bg-cyan-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
}
