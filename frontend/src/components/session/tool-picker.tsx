/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import Image from "next/image";
import { Search, Globe, Check, Wrench } from "lucide-react";
import type { SessionConnector } from "@/lib/session-utils";
import { invertLogoInDark, providerLogo } from "@/lib/connectors";
import { TOOL_CAPABILITIES } from "@/lib/tool-catalog";
import { cx } from "@/utils/cx";

type Props = {
  availableConnectors: SessionConnector[];
  selectedConnectorIds: string[];
  onToggleConnector: (id: string) => void;
  onToggleAllConnectors: (ids: string[]) => void;
  selectedToolIds: string[];
  onToggleTool: (id: string) => void;
  onToggleAllTools: (ids: string[]) => void;
  loading?: boolean;
};

type RowProps = {
  id: string;
  name: string;
  subtitle: string;
  checked: boolean;
  onToggle: () => void;
  logoSrc?: string | null;
  logoAlt?: string;
  invertLogo?: boolean;
};

function ToolRow({
  id,
  name,
  subtitle,
  checked,
  onToggle,
  logoSrc,
  logoAlt,
  invertLogo,
}: RowProps) {
  return (
    <button
      key={id}
      type="button"
      onClick={onToggle}
      className={cx(
        "group/item flex w-full items-center justify-between rounded-xl border px-2.5 py-2 text-left transition-all duration-200",
        checked
          ? "border-indigo-500/20 bg-indigo-500/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]"
          : "border-transparent hover:bg-zinc-100 dark:hover:bg-white/5",
      )}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <div
          className={cx(
            "flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-lg border transition-all duration-300",
            checked
              ? "border-indigo-500/40 bg-indigo-500/20 text-indigo-500 dark:text-indigo-400 shadow-[0_0_10px_rgba(99,102,241,0.2)]"
              : "border-zinc-200 bg-zinc-50 text-zinc-500 dark:border-white/10 dark:bg-white/5 group-hover/item:border-zinc-300 dark:group-hover/item:border-white/20 group-hover/item:text-zinc-700 dark:group-hover/item:text-zinc-300",
          )}
        >
          {logoSrc ? (
            <Image
              src={logoSrc}
              alt={logoAlt ?? name}
              width={18}
              height={18}
              className={cx("object-contain", invertLogo && "dark:invert")}
            />
          ) : (
            <Wrench className="h-4 w-4" />
          )}
        </div>
        <div className="flex min-w-0 flex-col">
          <div
            className={cx(
              "truncate text-xs font-semibold leading-tight transition-colors",
              checked
                ? "text-zinc-900 dark:text-white"
                : "text-zinc-600 dark:text-zinc-400 group-hover/item:text-zinc-900 dark:group-hover/item:text-zinc-200",
            )}
          >
            {name}
          </div>
          <div
            className={cx(
              "mt-0.5 truncate text-[9px] font-bold uppercase tracking-wider",
              checked ? "text-indigo-500/80 dark:text-indigo-400/80" : "text-zinc-400 dark:text-zinc-600",
            )}
          >
            {subtitle}
          </div>
        </div>
      </div>
      <div
        className={cx(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-300",
          checked
            ? "scale-110 border-indigo-500 bg-indigo-500 text-white shadow-[0_0_8px_rgba(99,102,241,0.4)]"
            : "border-zinc-300 bg-transparent text-transparent dark:border-zinc-700 group-hover/item:border-zinc-400 dark:group-hover/item:border-zinc-500",
        )}
      >
        <Check className="h-2.5 w-2.5 stroke-[4]" />
      </div>
    </button>
  );
}

function SectionHeader({
  title,
  onToggleAll,
}: {
  title: string;
  onToggleAll: () => void;
}) {
  return (
    <div className="flex items-center justify-between px-1 pt-2 pb-1">
      <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-zinc-500">
        {title}
      </span>
      <button
        type="button"
        onClick={onToggleAll}
        className="rounded-md px-2 py-1 text-[10px] font-bold text-indigo-500 transition-colors hover:bg-indigo-500/10 hover:text-indigo-400 dark:text-indigo-400 dark:hover:text-indigo-300"
      >
        Toggle All
      </button>
    </div>
  );
}

/** Tools/connectors list for embedding in the composer "+" menu. */
export function ToolPickerPanel({
  availableConnectors,
  selectedConnectorIds,
  onToggleConnector,
  onToggleAllConnectors,
  selectedToolIds,
  onToggleTool,
  onToggleAllTools,
  loading = false,
}: Props) {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();

  const connectors = availableConnectors.filter(
    (c) => c.connection_id !== "system",
  );

  const filteredCapabilities = TOOL_CAPABILITIES.filter((cap) => {
    if (!needle) return true;
    return (
      cap.label.toLowerCase().includes(needle) ||
      cap.id.toLowerCase().includes(needle) ||
      cap.description.toLowerCase().includes(needle) ||
      cap.tools.some((t) => t.toLowerCase().includes(needle))
    );
  });

  const filteredConnectors = connectors.filter((c) => {
    if (!needle) return true;
    return (
      c.name.toLowerCase().includes(needle) ||
      c.provider.toLowerCase().includes(needle) ||
      c.connection_id.toLowerCase().includes(needle)
    );
  });

  const capabilityIds = filteredCapabilities.map((c) => c.id);
  const connectorIds = filteredConnectors.map((c) => c.connection_id);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-1 shrink-0 px-1">
        <div className="group relative flex items-center">
          <Search className="absolute left-3 h-4 w-4 text-zinc-500 transition-colors group-focus-within:text-indigo-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tools & connectors..."
            className="w-full rounded-xl border border-zinc-200 bg-zinc-50 py-2 pl-10 pr-4 text-xs text-zinc-800 placeholder:text-zinc-400 transition-all focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500/50 dark:border-white/5 dark:bg-white/5 dark:text-zinc-200 dark:placeholder:text-zinc-600 dark:focus:bg-white/[0.08]"
            onKeyDown={(e) => e.stopPropagation()}
          />
        </div>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1 pb-1">
        {loading ? (
          <div className="space-y-2 px-1 py-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-2.5 rounded-xl px-2.5 py-2"
              >
                <div className="h-8 w-8 animate-pulse rounded-lg bg-zinc-200 dark:bg-white/10" />
                <div className="flex flex-1 flex-col gap-1.5">
                  <div className="h-3 w-28 animate-pulse rounded bg-zinc-200 dark:bg-white/10" />
                  <div className="h-2 w-16 animate-pulse rounded bg-zinc-100 dark:bg-white/5" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <>
            {filteredCapabilities.length > 0 && (
              <>
                <SectionHeader
                  title="Built-in"
                  onToggleAll={() => onToggleAllTools(capabilityIds)}
                />
                {filteredCapabilities.map((cap) => (
                  <ToolRow
                    key={cap.id}
                    id={cap.id}
                    name={cap.label}
                    subtitle={cap.description}
                    checked={selectedToolIds.includes(cap.id)}
                    onToggle={() => onToggleTool(cap.id)}
                  />
                ))}
              </>
            )}

            {(filteredConnectors.length > 0 || (!needle && connectors.length === 0)) && (
              <>
                <SectionHeader
                  title="Connectors"
                  onToggleAll={() => {
                    if (connectorIds.length) onToggleAllConnectors(connectorIds);
                  }}
                />
                {filteredConnectors.map((connector) => {
                  const logo = providerLogo(connector.provider);
                  return (
                    <ToolRow
                      key={connector.connection_id}
                      id={connector.connection_id}
                      name={connector.name}
                      subtitle={connector.provider}
                      checked={selectedConnectorIds.includes(connector.connection_id)}
                      onToggle={() => onToggleConnector(connector.connection_id)}
                      logoSrc={logo}
                      logoAlt={connector.provider}
                      invertLogo={invertLogoInDark(connector.provider)}
                    />
                  );
                })}
                {!needle && connectors.length === 0 && (
                  <div className="flex flex-col items-center justify-center gap-2 py-6">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-100 dark:bg-white/5">
                      <Globe className="h-5 w-5 text-zinc-400 dark:text-zinc-600" />
                    </div>
                    <p className="text-xs font-medium text-zinc-500">
                      No connectors connected
                    </p>
                  </div>
                )}
              </>
            )}

            {filteredCapabilities.length === 0 &&
              filteredConnectors.length === 0 &&
              needle && (
                <div className="flex flex-col items-center justify-center gap-3 py-10">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-zinc-100 dark:bg-white/5">
                    <Search className="h-6 w-6 text-zinc-400 dark:text-zinc-700" />
                  </div>
                  <p className="text-xs font-medium text-zinc-500">
                    No tools found for &quot;{search}&quot;
                  </p>
                </div>
              )}
          </>
        )}
      </div>
    </div>
  );
}
