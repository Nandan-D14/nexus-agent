/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Search, SlidersHorizontal, Wrench } from "lucide-react";
import type { SessionConnector } from "@/lib/session-utils";
import { invertLogoInDark, isGoogleProvider, providerLogo } from "@/lib/connectors";
import { useIntegrationsCatalogQuery } from "@/lib/queries/integrations";
import { TOOL_CAPABILITIES } from "@/lib/tool-catalog";
import { APP_CONNECTORS } from "@/lib/app-paths";
import { cx } from "@/utils/cx";

type Props = {
  availableConnectors: SessionConnector[];
  selectedConnectorIds: string[];
  onToggleConnector: (id: string) => void;
  selectedToolIds: string[];
  onToggleTool: (id: string) => void;
  loading?: boolean;
};

const FEATURED_PLUGIN_ORDER = [
  "gmail",
  "google_drive",
  "google_calendar",
  "google_tasks",
  "github",
  "linear",
  "vercel",
] as const;

const FEATURED_PLUGIN_NAMES: Record<string, string> = {
  gmail: "Gmail",
  google_drive: "Google Drive",
  google_calendar: "Google Calendar",
  google_tasks: "Google Tasks",
  github: "GitHub",
  linear: "Linear",
  vercel: "Vercel",
};

type PluginRow = {
  key: string;
  name: string;
  provider: string;
  connectionId?: string;
};

function matchConnection(
  provider: string,
  connectors: SessionConnector[],
): SessionConnector | undefined {
  const exact = connectors.find((c) => c.provider === provider);
  if (exact) return exact;
  if (isGoogleProvider(provider)) {
    return connectors.find((c) => isGoogleProvider(c.provider));
  }
  return undefined;
}

function PluginItem({
  name,
  provider,
  selected,
  onClick,
}: {
  name: string;
  provider: string;
  selected: boolean;
  onClick: () => void;
}) {
  const logoSrc = providerLogo(provider);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-[13px] transition-colors",
        selected
          ? "bg-dropdown-item-hover-background text-text-primary"
          : "text-text-primary hover:bg-dropdown-item-hover-background",
      )}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-sm">
        {logoSrc ? (
          <Image
            src={logoSrc}
            alt=""
            width={18}
            height={18}
            className={cx("object-contain", invertLogoInDark(provider) && "dark:invert")}
          />
        ) : (
          <Wrench className="h-3.5 w-3.5 text-text-tertiary" />
        )}
      </span>
      <span className="min-w-0 flex-1 truncate">{name}</span>
      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
    </button>
  );
}

/** Tools/connectors list for the composer "+" plugins flyout. */
export function ToolPickerPanel({
  availableConnectors,
  selectedConnectorIds,
  onToggleConnector,
  selectedToolIds,
  onToggleTool,
  loading = false,
}: Props) {
  const router = useRouter();
  const catalogQuery = useIntegrationsCatalogQuery();
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();

  const pluginRows = useMemo<PluginRow[]>(() => {
    const connectors = availableConnectors.filter((c) => c.connection_id !== "system");
    const catalog = catalogQuery.data ?? [];
    const catalogByProvider = new Map(catalog.map((item) => [item.provider, item]));
    const rows: PluginRow[] = [];
    const seen = new Set<string>();

    for (const provider of FEATURED_PLUGIN_ORDER) {
      const catalogItem = catalogByProvider.get(provider);
      const connection = matchConnection(provider, connectors);
      rows.push({
        key: provider,
        name: catalogItem?.name ?? FEATURED_PLUGIN_NAMES[provider] ?? provider,
        provider,
        connectionId: connection?.connection_id,
      });
      seen.add(provider);
    }

    for (const connector of connectors) {
      if (seen.has(connector.provider)) continue;
      rows.push({
        key: connector.connection_id,
        name: connector.name,
        provider: connector.provider,
        connectionId: connector.connection_id,
      });
      seen.add(connector.provider);
    }

    return rows;
  }, [availableConnectors, catalogQuery.data]);

  const connectors = availableConnectors.filter((c) => c.connection_id !== "system");

  const filteredPlugins = pluginRows.filter((row) => {
    if (!needle) return true;
    return (
      row.name.toLowerCase().includes(needle) || row.provider.toLowerCase().includes(needle)
    );
  });

  const filteredCapabilities = TOOL_CAPABILITIES.filter((cap) => {
    if (!needle) return true;
    return (
      cap.label.toLowerCase().includes(needle) ||
      cap.id.toLowerCase().includes(needle) ||
      cap.description.toLowerCase().includes(needle) ||
      cap.tools.some((t) => t.toLowerCase().includes(needle))
    );
  });

  const showSkeleton = loading && connectors.length === 0 && !catalogQuery.data;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 px-1 pb-1.5">
        <div className="relative flex items-center">
          <Search className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-text-tertiary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search plugins"
            className="w-full rounded-lg border border-input-border bg-background-secondary-default py-1.5 pl-8 pr-3 text-[13px] text-text-primary placeholder:text-text-placeholder outline-none focus:border-border-button-hover"
            onKeyDown={(e) => e.stopPropagation()}
          />
        </div>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1">
        {showSkeleton ? (
          <div className="space-y-1 py-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-2.5 rounded-lg px-2 py-2">
                <div className="h-5 w-5 animate-pulse rounded-sm bg-background-tertiary-default" />
                <div className="h-3 w-28 animate-pulse rounded bg-background-tertiary-default" />
              </div>
            ))}
          </div>
        ) : (
          <>
            {filteredPlugins.map((row) => {
              const selected = Boolean(
                row.connectionId && selectedConnectorIds.includes(row.connectionId),
              );
              return (
                <PluginItem
                  key={row.key}
                  name={row.name}
                  provider={row.provider}
                  selected={selected}
                  onClick={() => {
                    if (row.connectionId) {
                      onToggleConnector(row.connectionId);
                      return;
                    }
                    router.push(APP_CONNECTORS);
                  }}
                />
              );
            })}

            {filteredCapabilities.length > 0 && (
              <>
                <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-tertiary">
                  Built-in
                </div>
                {filteredCapabilities.map((cap) => {
                  const checked = selectedToolIds.includes(cap.id);
                  return (
                    <button
                      key={cap.id}
                      type="button"
                      onClick={() => onToggleTool(cap.id)}
                      className={cx(
                        "flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-[13px] transition-colors",
                        checked
                          ? "bg-dropdown-item-hover-background text-text-primary"
                          : "text-text-primary hover:bg-dropdown-item-hover-background",
                      )}
                    >
                      <Wrench className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
                      <span className="min-w-0 flex-1 truncate">{cap.label}</span>
                    </button>
                  );
                })}
              </>
            )}

            {filteredPlugins.length === 0 && filteredCapabilities.length === 0 && needle && (
              <p className="px-2 py-6 text-center text-[13px] text-text-tertiary">
                No plugins for &quot;{search}&quot;
              </p>
            )}
          </>
        )}
      </div>

      <div className="mt-1 shrink-0 border-t border-separator-border px-1 pt-1">
        <Link
          href={APP_CONNECTORS}
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] text-text-primary transition-colors hover:bg-dropdown-item-hover-background"
        >
          <SlidersHorizontal className="h-4 w-4 shrink-0 text-text-tertiary" />
          <span className="flex-1">Manage plugins</span>
        </Link>
      </div>
    </div>
  );
}
