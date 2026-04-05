"use client";

type Props = {
  streamUrl: string | null;
};

export function DesktopPanel({ streamUrl }: Props) {
  if (!streamUrl) {
    return (
      <div className="relative flex flex-col items-center justify-center h-full rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden group">
        {/* Scanning Effect Background */}
        <div className="absolute inset-0 opacity-20 pointer-events-none">
          <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,#22d3ee_50%,transparent_100%)] bg-[length:100%_4px] animate-[scan_3s_linear_infinite]" />
        </div>

        {/* Skeleton loading placeholder */}
        <div className="w-full h-full p-8 flex flex-col gap-6 animate-pulse opacity-40">
          <div className="flex items-center gap-4">
            <div className="h-3 w-32 rounded bg-zinc-800" />
            <div className="h-[1px] flex-1 bg-zinc-800" />
          </div>
          <div className="flex-1 rounded-xl bg-zinc-900/50 border border-zinc-800/50" />
          <div className="flex justify-between items-center">
            <div className="flex gap-3">
              <div className="h-2 w-16 rounded bg-zinc-800" />
              <div className="h-2 w-12 rounded bg-zinc-800" />
            </div>
            <div className="h-2 w-24 rounded bg-zinc-800" />
          </div>
        </div>

        <div className="absolute flex flex-col items-center gap-4">
          <div className="relative">
            <div className="absolute inset-0 bg-cyan-500/20 blur-xl animate-pulse" />
            <div className="relative w-12 h-12 rounded-full border border-cyan-500/30 flex items-center justify-center">
              <div className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_15px_rgba(34,211,238,0.8)]" />
            </div>
          </div>
          <div className="space-y-1 text-center">
            <p className="text-xs font-black text-cyan-400 uppercase tracking-[0.3em]">Establishing Link</p>
            <p className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest">Secure VNC Protocol Initialization...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full rounded-2xl border border-zinc-800 overflow-hidden bg-black shadow-inner shadow-black/80 group">
      {/* LIVE indicator */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2.5 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/5 transition-transform group-hover:scale-105">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
        </span>
        <span className="text-emerald-400 text-[10px] font-black uppercase tracking-[0.2em]">
          Live Stream
        </span>
      </div>

      <iframe
        src={streamUrl}
        className="w-full h-full border-0 grayscale-[0.15] contrast-[1.1] brightness-[1.05]"
        allow="clipboard-read; clipboard-write"
        title="CoComputer Desktop"
      />
      
      {/* Subtle Overlay Border */}
      <div className="absolute inset-0 border border-white/5 pointer-events-none rounded-2xl" />
    </div>
  );
}
