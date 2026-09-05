/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import {
  useEffect,
  useRef,
  useState,
  memo,
  type CSSProperties,
} from "react";
import styles from "./todo-list.module.css";

export type TodoItem = {
  title: string;
  status: "pending" | "in_progress" | "done";
  note?: string;
};

interface TodoListProps {
  items: TodoItem[];
  defaultExpanded?: boolean;
}

const cls = (base: string, on?: boolean) => base + (on ? " " + styles.on : "");

function CheckIcon({ on }: { on?: boolean }) {
  return (
    <svg
      className={
        cls(styles.todoIcon, on) +
        " absolute inset-0 h-4 w-4 transition-opacity duration-200 " +
        (on ? "text-emerald-500 opacity-100" : "text-text-tertiary opacity-0")
      }
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden
    >
      <path
        d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ArrowIcon({ on }: { on?: boolean }) {
  return (
    <svg
      className={
        cls(styles.todoIcon + " " + styles.strong, on) +
        " absolute inset-0 h-4 w-4 text-blue-500 transition-opacity duration-200 " +
        (on ? "opacity-100" : "opacity-0")
      }
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden
    >
      <path
        d="m12.75 15 3-3m0 0-3-3m3 3h-7.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DashedIcon({ on }: { on?: boolean }) {
  return (
    <svg
      className={
        cls(styles.todoIcon, on) +
        " absolute inset-0 h-4 w-4 text-text-tertiary transition-opacity duration-200 " +
        (on ? "opacity-100" : "opacity-0")
      }
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeDasharray="1.8 3.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RollDigit({ char }: { char: string }) {
  const prev = useRef(char);
  const [roll, setRoll] = useState<{ from: string; to: string } | null>(null);
  const [up, setUp] = useState(false);

  useEffect(() => {
    if (char === prev.current) return;
    const from = prev.current;
    prev.current = char;
    setRoll({ from, to: char });
    setUp(false);
    const raf = requestAnimationFrame(() =>
      requestAnimationFrame(() => setUp(true)),
    );
    const done = setTimeout(() => setRoll(null), 380);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(done);
    };
  }, [char]);

  if (!roll) return <span className={styles.rollDigit}>{char}</span>;
  return (
    <span className={styles.rollDigit}>
      <span className={cls(styles.rollInner, up)}>
        <span>{roll.from}</span>
        <span>{roll.to}</span>
      </span>
    </span>
  );
}

function RollingCount({ value }: { value: string }) {
  return (
    <span className={styles.rollCount} aria-label={value}>
      {value.split("").map((c, i) => (
        <RollDigit key={`${i}-${c === "/" ? "slash" : "d"}`} char={c} />
      ))}
    </span>
  );
}

function FilledCheckIcon() {
  return (
    <svg className={styles.todoHeadCheck} viewBox="0 0 24 24" width="16" height="16" aria-hidden>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm13.36-1.814a.75.75 0 1 0-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 0 0-1.06 1.06l2.25 2.25a.75.75 0 0 0 1.14-.094l3.75-5.25Z"
        fill="currentColor"
      />
    </svg>
  );
}

/** Cursor-style to-do list — pie header, rolling count, layered status icons. */
export const TodoList = memo(function TodoList({
  items,
  defaultExpanded = false,
}: TodoListProps) {
  const hasActive = items.some((i) => i.status === "in_progress");
  const [collapsed, setCollapsed] = useState(
    () => !(defaultExpanded || hasActive),
  );

  // Expand when a task becomes active (don't leave the list stuck shut).
  useEffect(() => {
    if (hasActive) setCollapsed(false);
  }, [hasActive]);

  if (!items || items.length === 0) return null;

  const total = items.length;
  const completed = items.filter((i) => i.status === "done").length;
  const allDone = completed === total && total > 0;
  const running = hasActive || (completed > 0 && !allDone);
  const pct = Math.round((completed / total) * 100);

  return (
    <div className={styles.todo + " mb-3 w-full text-text-primary select-none"}>
      <button
        type="button"
        className={styles.todoHead + " flex w-full cursor-pointer items-center gap-2 rounded-lg px-1 py-1.5 text-left"}
        aria-expanded={!collapsed}
        aria-label="Toggle to-dos"
        onClick={() => setCollapsed((c) => !c)}
      >
        <span className={styles.todoHeadIcon + " relative inline-flex h-5 w-5 shrink-0 items-center justify-center"}>
          {allDone ? (
            <FilledCheckIcon />
          ) : running ? (
            <span
              className={styles.todoHeadPie}
              style={{ ["--todo-pie" as string]: `${pct}%` } as CSSProperties}
              aria-hidden
            >
              <svg className={styles.todoHeadPieRing} viewBox="0 0 24 24">
                <circle
                  cx="12"
                  cy="12"
                  r="10.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeDasharray="2.2 4.4"
                  strokeLinecap="round"
                />
              </svg>
            </span>
          ) : (
            <svg
              className={styles.todoListIcon}
              viewBox="0 0 24 24"
              width="16"
              height="16"
              aria-hidden
            >
              <path
                d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
          <svg className={styles.todoChevron} viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path
              d="m19.5 8.25-7.5 7.5-7.5-7.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span className={styles.todoTitle + " text-sm font-medium text-text-primary"}>To-dos</span>
        <span className={styles.todoCount + " text-text-tertiary tabular-nums"}>
          <RollingCount value={`${completed}/${total}`} />
        </span>
      </button>

      <div className={styles.todoCollapsible + (collapsed ? " " + styles.isCollapsed : "") + " grid"}>
        <div className={styles.todoInner + " min-h-0 overflow-hidden"}>
          <ul className={styles.todoList + " m-0 flex list-none flex-col gap-0.5 p-0 pt-1 pl-1"}>
            {items.map((item, i) => {
              const done = item.status === "done";
              const active = item.status === "in_progress";
              return (
                <li
                  key={`${item.title}-${i}`}
                  className={
                    styles.todoItem +
                    (done ? " " + styles.done : active ? " " + styles.active : "") +
                    " flex items-start gap-2.5 rounded-md px-2 py-1.5"
                  }
                  style={{ ["--i" as string]: i } as CSSProperties}
                >
                  <span className={styles.todoIconWrap + " relative mt-0.5 h-4 w-4 shrink-0"}>
                    <DashedIcon on={!done && !active} />
                    <ArrowIcon on={active} />
                    <CheckIcon on={done} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <span
                      className={
                        styles.todoLabel +
                        " block min-w-0 flex-1 text-[0.8125rem] leading-[1.35] text-text-secondary " +
                        (done ? "text-text-tertiary line-through" : active ? "font-medium text-text-primary" : "")
                      }
                      data-label={item.title}
                    >
                      {item.title}
                    </span>
                    {item.note ? (
                      <div className={styles.todoNote + " mt-0.5 text-xs leading-snug text-text-tertiary"}>
                        {item.note}
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
});
