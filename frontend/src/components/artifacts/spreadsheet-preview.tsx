/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import * as XLSX from "xlsx";
import { Loader2 } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import { resolveArtifactUrl } from "@/lib/artifact-url";
import { cn } from "@/lib/utils";

const ROW_CAP = 2000;

function cellText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return String(value);
}

export function SpreadsheetPreview({ artifact }: { artifact: RunArtifact }) {
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState("");
  const [tables, setTables] = useState<Record<string, string[][]>>({});
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    resolveArtifactUrl(artifact, { forPreview: false })
      .then(async (url) => {
        if (cancelled) return;
        if (!url) throw new Error("missing url");
        const res = await fetch(url);
        if (!res.ok) throw new Error("fetch failed");
        const buffer = await res.arrayBuffer();
        const workbook = XLSX.read(buffer, { type: "array" });
        const parsed: Record<string, string[][]> = {};
        let anyTruncated = false;
        const names = workbook.SheetNames.length > 0 ? workbook.SheetNames : ["Sheet1"];
        for (const name of names) {
          const sheet = workbook.Sheets[name];
          const rows = sheet
            ? (XLSX.utils.sheet_to_json<unknown[]>(sheet, {
                header: 1,
                raw: false,
                defval: "",
                blankrows: false,
              }) as unknown[][])
            : [];
          const normalized = rows.map((row) =>
            Array.isArray(row) ? row.map(cellText) : [],
          );
          if (normalized.length > ROW_CAP) {
            anyTruncated = true;
            parsed[name] = normalized.slice(0, ROW_CAP);
          } else {
            parsed[name] = normalized;
          }
        }
        if (cancelled) return;
        setTables(parsed);
        setSheetNames(names);
        setActiveSheet(names[0] ?? "Sheet1");
        setTruncated(anyTruncated);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this spreadsheet.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact]);

  const rows = tables[activeSheet] ?? [];
  const colCount = useMemo(
    () => Math.max(1, ...rows.map((row) => row.length), 1),
    [rows],
  );
  const columns = useMemo(
    () => Array.from({ length: colCount }, (_, index) => XLSX.utils.encode_col(index)),
    [colCount],
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading spreadsheet…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f4f4f5]">
      {truncated ? (
        <p className="shrink-0 border-b border-zinc-200 bg-amber-50 px-4 py-2 text-[12px] text-amber-900">
          Showing the first {ROW_CAP.toLocaleString()} rows. Download the file to see
          everything.
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto custom-scrollbar">
        <table className="min-w-full border-collapse text-left text-[12px] tabular-nums">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="sticky left-0 z-20 w-10 min-w-10 border-b border-r border-zinc-200 bg-zinc-100 px-1 py-1.5 text-center text-[10px] font-medium text-zinc-400" />
              {columns.map((label) => (
                <th
                  key={label}
                  className="min-w-[5.5rem] border-b border-r border-zinc-200 bg-zinc-100 px-2 py-1.5 text-center text-[10px] font-medium text-zinc-500"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={colCount + 1}
                  className="px-4 py-10 text-center text-sm text-zinc-500"
                >
                  This sheet is empty.
                </td>
              </tr>
            ) : (
              rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="bg-white even:bg-zinc-50">
                  <th className="sticky left-0 z-10 w-10 min-w-10 border-b border-r border-zinc-200 bg-zinc-100 px-1 py-1 text-center text-[10px] font-medium text-zinc-400">
                    {rowIndex + 1}
                  </th>
                  {columns.map((_, colIndex) => (
                    <td
                      key={colIndex}
                      className="max-w-[20rem] truncate border-b border-r border-zinc-200 px-2 py-1 text-zinc-800"
                      title={row[colIndex] || undefined}
                    >
                      {row[colIndex] ?? ""}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {sheetNames.length > 0 ? (
        <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-t border-zinc-200 bg-zinc-100 px-2 py-1.5">
          {sheetNames.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setActiveSheet(name)}
              className={cn(
                "shrink-0 rounded-md px-2.5 py-1 text-[12px] font-medium",
                name === activeSheet
                  ? "bg-white text-zinc-900 shadow-sm"
                  : "text-zinc-500 hover:bg-white/70 hover:text-zinc-800",
              )}
            >
              {name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
