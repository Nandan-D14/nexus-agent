/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import { MoreHorizontal, Plus, Power, Trash2 } from "lucide-react";

import {
  Dropdown,
  DropdownGroup,
  DropdownItem,
  DropdownPopover,
  DropdownTrigger,
} from "@/components/base/dropdown/dropdown";
import { ConnectorLogo } from "@/components/connectors/connector-logo";
import type { CatalogItem, IntegrationConnection } from "@/lib/connectors";
import { isGoogleProvider } from "@/lib/connectors";
import { cx } from "@/utils/cx";

type Props = {
  item: CatalogItem;
  connected: boolean;
  connection?: IntegrationConnection;
  rowId: string;
  onOpen: () => void;
  onToggle?: () => void;
  onDisconnect?: () => void;
};

export function ConnectorRow({
  item,
  connected,
  connection,
  rowId,
  onOpen,
  onToggle,
  onDisconnect,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const canToggle = Boolean(connection && !isGoogleProvider(item.provider) && onToggle);

  return (
    <div
      id={rowId}
      className={cx(
        "group flex items-center gap-3 rounded-2xl px-3 py-2.5 transition-colors",
        "hover:bg-zinc-100 dark:hover:bg-zinc-800/80",
        menuOpen && "bg-zinc-100 dark:bg-zinc-800/80",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <ConnectorLogo provider={item.provider} name={item.name} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {item.name}
          </span>
          <span className="block truncate text-sm text-zinc-500">{item.description}</span>
        </span>
      </button>
      {connected ? (
        <Dropdown isOpen={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownTrigger
            aria-label={`Actions for ${item.name}`}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-200 hover:text-zinc-800 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
          >
            <MoreHorizontal className="size-4" />
          </DropdownTrigger>
          <DropdownPopover aria-label="Connector actions" placement="bottom end" className="w-[180px]">
            <DropdownGroup>
              <DropdownItem
                onSelect={() => {
                  setMenuOpen(false);
                  onOpen();
                }}
              >
                <span>Details</span>
              </DropdownItem>
              {canToggle ? (
                <DropdownItem
                  onSelect={() => {
                    setMenuOpen(false);
                    onToggle?.();
                  }}
                >
                  <Power className="size-4" />
                  <span>{connection?.enabled === false ? "Enable" : "Disable"}</span>
                </DropdownItem>
              ) : null}
              {onDisconnect ? (
                <DropdownItem
                  onSelect={() => {
                    setMenuOpen(false);
                    onDisconnect();
                  }}
                  className="text-red-500 hover:bg-red-500/10 focus-visible:bg-red-500/10"
                >
                  <Trash2 className="size-4" />
                  <span>Disconnect</span>
                </DropdownItem>
              ) : null}
            </DropdownGroup>
          </DropdownPopover>
        </Dropdown>
      ) : (
        <button
          type="button"
          aria-label={`Open ${item.name}`}
          onClick={onOpen}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
        >
          <Plus className="size-4" />
        </button>
      )}
    </div>
  );
}
