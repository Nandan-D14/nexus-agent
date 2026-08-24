"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button as AriaButton,
  Dialog,
  DialogTrigger,
  Popover as AriaPopover,
} from "react-aria-components";
import { RiSearchLine } from "@remixicon/react";
import {
  MENU_ITEM,
  MENU_ITEM_ACTIVE,
  MENU_POPOVER_SURFACE,
} from "@/components/base/dropdown/menu-styles";
import { ChevronDownSmall } from "@/components/foundations/icons/chevrons";
import { cx } from "@/utils/cx";
import { useDismissOnOutsidePress, useTriggerToggle } from "@/utils/use-dismiss-on-outside-press";

export function LlmModelComboBox({
  models,
  value,
  onChange,
  loading = false,
  disabled = false,
  placeholder = "Select a model",
}: {
  models: string[];
  value: string;
  onChange: (value: string) => void;
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const selectedRef = useRef<HTMLButtonElement>(null);
  const allowOpenChange = useTriggerToggle(open, triggerRef);
  useDismissOnOutsidePress(open, () => setOpen(false), [triggerRef, popoverRef]);

  const allModels = useMemo(
    () => Array.from(new Set([...models, value].filter(Boolean))),
    [models, value],
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return allModels;
    return allModels.filter((id) => id.toLowerCase().includes(needle));
  }, [allModels, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const focusTimer = window.setTimeout(() => searchRef.current?.focus(), 20);
    const scrollTimer = window.setTimeout(() => {
      selectedRef.current?.scrollIntoView({ block: "nearest" });
    }, 40);
    return () => {
      window.clearTimeout(focusTimer);
      window.clearTimeout(scrollTimer);
    };
  }, [open]);

  return (
    <DialogTrigger
      isOpen={open}
      onOpenChange={(next) => {
        if (disabled) return;
        if (allowOpenChange(next)) setOpen(next);
      }}
    >
      <AriaButton
        ref={triggerRef}
        aria-label="LLM model"
        isDisabled={disabled}
        className={cx(
          "flex h-8 w-[220px] shrink-0 cursor-pointer items-center justify-between rounded-2lg",
          "border border-border-button-default bg-background-primary-default px-2.5 shadow-xs",
          "text-left text-body-2-medium text-text-primary",
          "hover:border-border-button-hover hover:bg-background-primary-hover",
          "outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
          "disabled:cursor-not-allowed disabled:bg-background-primary-disabled disabled:text-text-tertiary",
        )}
      >
        <span className="min-w-0 truncate">
          {loading && !value
            ? "Loading models…"
            : value || placeholder}
        </span>
        <ChevronDownSmall
          className={cx(
            "size-4 shrink-0 text-text-secondary transition-transform duration-200",
            open && "rotate-180",
            loading && "animate-pulse",
          )}
        />
      </AriaButton>
      <AriaPopover
        ref={popoverRef}
        isNonModal
        offset={4}
        placement="bottom start"
        className={cx(
          MENU_POPOVER_SURFACE,
          "z-[200] flex w-[min(380px,calc(100vw-32px))] flex-col overflow-hidden p-2",
        )}
      >
        <Dialog className="flex min-h-0 flex-col outline-none" aria-label="Select a model">
          <div className="relative mb-1.5 shrink-0">
            <RiSearchLine
              className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-text-tertiary"
              aria-hidden
            />
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${allModels.length} models`}
              aria-label="Search models"
              className={cx(
                "h-8 w-full rounded-2lg border border-border-button-default bg-background-secondary-default",
                "pl-7 pr-2.5 text-body-2-medium text-text-primary outline-none",
                "placeholder:text-text-tertiary",
                "focus:ring-2 focus:ring-border-focus-ring",
              )}
            />
          </div>
          <div className="min-h-0 max-h-[280px] overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-2 py-3 text-body-2-regular text-text-secondary">
                {allModels.length === 0
                  ? loading
                    ? "Loading models…"
                    : "No models loaded yet."
                  : `No models match “${query.trim()}”.`}
              </p>
            ) : (
              <div className="flex flex-col gap-0.5" role="listbox" aria-label="Models">
                {filtered.map((id) => {
                  const selected = id === value;
                  return (
                    <button
                      key={id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      ref={selected ? selectedRef : undefined}
                      onClick={() => {
                        onChange(id);
                        setOpen(false);
                      }}
                      className={cx(
                        MENU_ITEM,
                        "px-2 py-1.5 font-mono text-body-2-medium",
                        selected && MENU_ITEM_ACTIVE,
                      )}
                    >
                      <span className="min-w-0 break-all text-left">{id}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <p className="shrink-0 px-2 pt-1.5 text-body-2-regular text-text-tertiary">
            {query.trim()
              ? `${filtered.length} of ${allModels.length}`
              : `${allModels.length} models`}
          </p>
        </Dialog>
      </AriaPopover>
    </DialogTrigger>
  );
}
