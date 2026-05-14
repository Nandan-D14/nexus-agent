/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Link2, Globe, Check } from "lucide-react";
import type { SessionConnector } from "@/lib/session-utils";
import { providerLogo } from "@/lib/session-utils";

type Props = {
  availableConnectors: SessionConnector[];
  selectedConnectorIds: string[];
  onToggleConnector: (id: string) => void;
  onToggleAll: (ids: string[]) => void;
};

export function ToolPicker({
  availableConnectors,
  selectedConnectorIds,
  onToggleConnector,
  onToggleAll,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const filteredConnectors = availableConnectors.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleToggleAll = () => {
    const filteredIds = filteredConnectors.map((c) => c.connection_id);
    onToggleAll(filteredIds);
  };

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors flex items-center gap-1.5"
        title="Links"
      >
        <Link2 className="w-4 h-4" />
        {selectedConnectorIds.length > 0 && (
          <span className="text-[10px] bg-indigo-500 text-white rounded-full w-4 h-4 flex items-center justify-center font-bold">
            {selectedConnectorIds.length}
          </span>
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="absolute left-0 bottom-full mb-3 w-80 rounded-[24px] border border-white/10 bg-zinc-950/90 backdrop-blur-2xl p-2 shadow-[0_20px_50px_rgba(0,0,0,0.5)] z-50 overflow-hidden"
          >
            {/* Search & Actions Header */}
            <div className="px-2 py-2 flex flex-col gap-3 border-b border-white/5 mb-2">
              <div className="relative flex items-center group">
                <Search className="absolute left-3 w-4 h-4 text-zinc-500 group-focus-within:text-indigo-400 transition-colors" />
                <input
                  autoFocus
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search tools & connectors..."
                  className="w-full bg-white/5 border border-white/5 rounded-xl pl-10 pr-4 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 focus:bg-white/[0.08] transition-all"
                />
              </div>
              <div className="flex items-center justify-between px-1">
                <span className="text-[10px] uppercase tracking-[0.15em] font-bold text-zinc-500">
                  Available Tools
                </span>
                <button
                  type="button"
                  onClick={handleToggleAll}
                  className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors px-2 py-1 rounded-md hover:bg-indigo-500/10"
                >
                  Toggle All
                </button>
              </div>
            </div>

            {/* Scrollable List */}
            <div className="max-h-60 overflow-y-auto custom-scrollbar space-y-0.5 px-1 pb-1">
              {filteredConnectors.map((connector) => {
                const checked = selectedConnectorIds.includes(connector.connection_id);
                const logo = providerLogo(connector.provider);
                return (
                  <button
                    key={connector.connection_id}
                    type="button"
                    onClick={() => onToggleConnector(connector.connection_id)}
                    className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left transition-all duration-200 group/item ${
                      checked
                        ? "bg-indigo-500/10 border border-indigo-500/20 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]"
                        : "hover:bg-white/5 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center border transition-all duration-300 overflow-hidden ${
                          checked
                            ? "border-indigo-500/40 bg-indigo-500/20 text-indigo-400 shadow-[0_0_10px_rgba(99,102,241,0.2)]"
                            : "border-white/10 bg-white/5 text-zinc-500 group-hover/item:text-zinc-300 group-hover/item:border-white/20"
                        }`}
                      >
                        {logo ? (
                          <Image
                            src={logo}
                            alt={connector.provider}
                            width={18}
                            height={18}
                            className={`object-contain ${
                              connector.provider === "github" ? "dark:invert" : ""
                            }`}
                          />
                        ) : (
                          <Globe className="w-4 h-4" />
                        )}
                      </div>
                      <div className="flex flex-col">
                        <div
                          className={`text-xs font-semibold leading-tight transition-colors ${
                            checked ? "text-white" : "text-zinc-400 group-hover/item:text-zinc-200"
                          }`}
                        >
                          {connector.name}
                        </div>
                        <div
                          className={`text-[9px] uppercase tracking-wider mt-0.5 font-bold ${
                            checked ? "text-indigo-400/80" : "text-zinc-600"
                          }`}
                        >
                          {connector.provider}
                        </div>
                      </div>
                    </div>
                    <div
                      className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
                        checked
                          ? "border-indigo-500 bg-indigo-500 text-white scale-110 shadow-[0_0_8px_rgba(99,102,241,0.4)]"
                          : "border-zinc-700 bg-transparent text-transparent group-hover/item:border-zinc-500"
                      }`}
                    >
                      <Check className="w-2.5 h-2.5 stroke-[4]" />
                    </div>
                  </button>
                );
              })}

              {filteredConnectors.length === 0 && (
                <div className="py-12 flex flex-col items-center justify-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center">
                    <Search className="w-6 h-6 text-zinc-700" />
                  </div>
                  <p className="text-xs text-zinc-600 font-medium">
                    No tools found for &quot;{search}&quot;
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
