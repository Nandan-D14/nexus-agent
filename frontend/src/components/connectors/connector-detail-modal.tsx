/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Loader2 } from "lucide-react";

import { ConnectorLogo } from "@/components/connectors/connector-logo";
import { ConnectorModal } from "@/components/connectors/connector-modal";
import {
  connectorDetail,
  isGoogleProvider,
  type CatalogItem,
  type IntegrationConnection,
} from "@/lib/connectors";

type Props = {
  item: CatalogItem;
  connected: boolean;
  connection?: IntegrationConnection;
  connecting?: boolean;
  onClose: () => void;
  onConnect: () => void;
  onToggle?: () => void;
  onDisconnect?: () => void;
  secondaryAction?: { label: string; onClick: () => void };
};

export function ConnectorDetailModal({
  item,
  connected,
  connection,
  connecting = false,
  onClose,
  onConnect,
  onToggle,
  onDisconnect,
  secondaryAction,
}: Props) {
  const detail = connectorDetail(item);
  const disabled = connection?.enabled === false;
  const canToggle = Boolean(connected && connection && !isGoogleProvider(item.provider) && onToggle);

  return (
    <ConnectorModal title="" onClose={onClose} hideHeader>
      <div className="space-y-5">
        <div className="flex items-start gap-4">
          <ConnectorLogo provider={item.provider} name={item.name} />
          <div className="min-w-0">
            <h2 className="font-serif text-xl tracking-tight text-zinc-900 dark:text-zinc-100">{item.name}</h2>
            <p className="mt-1 text-sm text-zinc-500">
              {connected ? (disabled ? "Installed · disabled" : "Installed") : "Not connected"}
            </p>
          </div>
        </div>

        <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">{detail.summary}</p>

        {detail.capabilities.length > 0 ? (
          <ul className="space-y-1.5 text-sm text-zinc-600 dark:text-zinc-400">
            {detail.capabilities.map((capability) => (
              <li key={capability} className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-zinc-400" />
                <span>{capability}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <p className="text-xs leading-5 text-zinc-500">{detail.connectHint}</p>

        {connected ? (
          <div className="flex flex-col gap-2 sm:flex-row">
            {canToggle ? (
              <button
                type="button"
                onClick={onToggle}
                className="inline-flex flex-1 items-center justify-center rounded-xl border border-zinc-200 px-4 py-3 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-800"
              >
                {disabled ? "Enable" : "Disable"}
              </button>
            ) : null}
            {onDisconnect ? (
              <button
                type="button"
                onClick={onDisconnect}
                className="inline-flex flex-1 items-center justify-center rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-600 hover:bg-red-500/15 dark:text-red-400"
              >
                Disconnect
              </button>
            ) : null}
          </div>
        ) : (
          <div className="space-y-2">
            <button
              type="button"
              onClick={onConnect}
              disabled={connecting}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-900 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-zinc-800 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              {connecting ? <Loader2 className="size-4 animate-spin" /> : null}
              Connect
            </button>
            {secondaryAction ? (
              <button
                type="button"
                onClick={secondaryAction.onClick}
                disabled={connecting}
                className="w-full text-center text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300"
              >
                {secondaryAction.label}
              </button>
            ) : null}
          </div>
        )}
      </div>
    </ConnectorModal>
  );
}
