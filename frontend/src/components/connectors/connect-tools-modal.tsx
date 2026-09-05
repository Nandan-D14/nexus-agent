/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect } from "react";
import { ArrowRight, Check, Ellipsis, Loader2, Plus, Puzzle, ShieldCheck, X } from "lucide-react";

import { ConnectorLogo } from "@/components/connectors/connector-logo";
import { QUICK_CONNECT_LABELS, type CatalogItem } from "@/lib/connectors";
import { cx } from "@/utils/cx";

export type ConnectToolsTile = {
  item: CatalogItem;
  connected: boolean;
};

type Props = {
  open: boolean;
  tiles: ConnectToolsTile[];
  connectingProvider: string | null;
  error: string | null;
  onConnect: (provider: string) => void;
  onBrowseAll: () => void;
  onClose: () => void;
};

export function ConnectToolsModal({
  open,
  tiles,
  connectingProvider,
  error,
  onConnect,
  onBrowseAll,
  onClose,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const connectedCount = tiles.filter((tile) => tile.connected).length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Connect your tools"
    >
      <div className="animate-pop-in w-full max-w-2xl rounded-2xl border border-border-button-default bg-background-primary-default shadow-xl">
        <div className="relative overflow-hidden rounded-2xl px-6 py-8 sm:px-10">
          <div
            aria-hidden
            className="pointer-events-none absolute -top-28 left-1/2 h-56 w-[32rem] -translate-x-1/2 rounded-full bg-blue-500/10 blur-3xl"
          />

          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute top-4 right-4 rounded-lg p-1.5 text-foreground-icon-secondary transition hover:bg-background-primary-hover hover:text-foreground-icon-hover"
          >
            <X className="size-4" />
          </button>

          <div className="relative flex flex-col items-center text-center">
            <span className="flex size-14 items-center justify-center rounded-2xl bg-notification-information-background">
              <Puzzle className="size-6 text-notification-information-foreground" />
            </span>

            <h2 className="mt-5 text-title-1-semibold text-text-primary">Connect your tools</h2>
            <p className="mt-2 max-w-md text-body-regular text-text-secondary">
              Integrate your favorite apps and services to bring more power to your AI agents.
            </p>
            <p className="mt-3 rounded-full bg-background-secondary-default px-3 py-1 text-caption-1-medium text-text-secondary">
              {connectedCount} of {tiles.length} connected
            </p>
          </div>

          <div className="relative mt-6 grid grid-cols-3 gap-3 sm:grid-cols-6">
            {tiles.map(({ item, connected }, index) => {
              const connecting = connectingProvider === item.provider;
              return (
                <button
                  key={item.provider}
                  type="button"
                  onClick={() => onConnect(item.provider)}
                  disabled={connecting || connected}
                  title={connected ? "Connected" : `Connect ${item.name}`}
                  aria-label={connected ? `${item.name} connected` : `Connect ${item.name}`}
                  style={{ animationDelay: `${Math.min(index, 5) * 45}ms` }}
                  className={cx(
                    "animate-fade-up flex flex-col items-center gap-2 rounded-2xl border border-border-button-default bg-background-primary-default p-4 shadow-card transition",
                    connected
                      ? "cursor-default border-border-focus-ring"
                      : "hover:border-border-button-hover hover:bg-background-primary-hover",
                  )}
                >
                  <span className="relative">
                    <ConnectorLogo provider={item.provider} name={item.name} />
                    {connecting ? (
                      <span className="absolute inset-0 flex items-center justify-center rounded-xl bg-background-full/70">
                        <Loader2 className="size-5 animate-spin text-foreground-icon-primary" />
                      </span>
                    ) : null}
                  </span>
                  <span className="text-caption-1-medium text-text-secondary">
                    {QUICK_CONNECT_LABELS[item.provider] ?? item.name}
                  </span>
                  <span className="flex h-5 items-center" aria-hidden={connected ? undefined : true}>
                    {connected ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-status-blue-background px-2 py-0.5 text-caption-2-semibold text-status-blue-text">
                        <Check className="size-3" />
                        Connected
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}

            <button
              type="button"
              onClick={onBrowseAll}
              title="Browse all integrations"
              aria-label="Browse all integrations"
              style={{ animationDelay: `${Math.min(tiles.length, 5) * 45}ms` }}
              className="animate-fade-up flex flex-col items-center gap-2 rounded-2xl border border-border-button-default bg-background-primary-default p-4 shadow-card transition hover:border-border-button-hover hover:bg-background-primary-hover"
            >
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-background-tertiary-default">
                <Ellipsis className="size-5 text-foreground-icon-secondary" />
              </span>
              <span className="text-caption-1-medium text-text-secondary">More</span>
              <span className="flex h-5 items-center" aria-hidden />
            </button>
          </div>

          {error ? (
            <p className="relative mt-4 text-center text-body-2-regular text-text-error-primary">
              {error}
            </p>
          ) : null}

          <div className="relative mt-6 flex flex-col gap-4 border-y border-separator-border py-5 sm:flex-row sm:items-center">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-notification-information-background">
              <ShieldCheck className="size-6 text-notification-information-foreground" />
            </span>
            <div className="min-w-0 flex-1 text-left">
              <p className="text-body-semibold text-text-primary">
                Secure: Your data, your control
              </p>
              <p className="mt-1 text-caption-1-regular text-text-secondary">
                We use industry-leading security to keep your data safe. You can disconnect apps at
                any time.
              </p>
            </div>
            <button
              type="button"
              onClick={onBrowseAll}
              className="inline-flex shrink-0 items-center gap-1.5 text-body-medium text-button-ghost-foreground transition hover:underline"
            >
              Learn more
              <ArrowRight className="size-4" />
            </button>
          </div>

          <div className="relative mt-6 flex flex-col-reverse items-stretch justify-center gap-2 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center justify-center rounded-2lg border border-border-button-default bg-background-primary-default px-5 py-3 text-body-semibold text-text-primary shadow-xs transition hover:bg-background-primary-hover hover:border-border-button-hover"
            >
              Not now
            </button>
            <button
              type="button"
              onClick={onBrowseAll}
              className="inline-flex items-center justify-center gap-2 rounded-2lg bg-button-primary px-6 py-3 text-body-semibold text-text-white shadow-xs"
            >
              <Plus className="size-4" />
              Browse all integrations
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
