/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import * as XLSX from "xlsx";
import { Download, Loader2 } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  downloadArtifactFile,
  getLastArtifactResolveError,
  isCsvArtifact,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { authenticatedFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const ROW_CAP = 2000;

function cellText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return String(value);
}

function looksLikeHeaderRow(row: string[] | undefined): boolean {
  if (!row || row.length === 0) return false;
  const filled = row.filter((cell) => cell.trim().length > 0);
  if (filled.length === 0) return false;
  const numeric = filled.filter((cell) => /^-?\d+(\.\d+)?$/.test(cell.trim()));
  return numeric.length / filled.length < 0.5;
}

export function SpreadsheetPreview({ artifact }: { artifact: RunArtifact }) {
  const csv = isCsvArtifact(artifact);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState("");
  const [tables, setTables] = useState<Record<string, string[][]>>({});
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ row: number; col: number } | null>(null);

  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelected(null);
    // Durable-first: immutable GCS copy for all sessions. Never depend on the
    // live sandbox (paused after ~5m) for delivered sheets.
    resolveArtifactUrl(artifact, { forPreview: false, allowSandbox: false })
      .then(async (url) => {
        if (cancelled) return;
        if (!url) {
          const code = getLastArtifactResolveError();
          if (code === "ARTIFACT_BLOB_MISSING") throw new Error("original-missing");
          throw new Error("missing url");
        }
        const res =
          url.startsWith("blob:") || url.startsWith("data:") || url.startsWith("http")
            ? await fetch(url)
            : await authenticatedFetch(url);
        if (!res.ok) throw new Error("fetch failed");
        const buffer = await res.arrayBuffer();
        const workbook = XLSX.read(buffer, { type: "array" });
        const parsed: Record<string, string[][]> = {};
        let anyTruncated = false;
        const names = workbook.SheetNames.length > 0 ? workbook.SheetNames : [csv ? "CSV" : "Sheet1"];
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
        setActiveSheet(names[0] ?? (csv ? "CSV" : "Sheet1"));
        setTruncated(anyTruncated);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof Error && err.message === "original-missing") {
          setError("Original file is no longer available - please regenerate. New files are stored durably.");
        } else {
          setError("Could not load this spreadsheet. Check connection and retry, or download the original.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact, csv]);

  const rows = tables[activeSheet] ?? [];
  const colCount = useMemo(
    () => Math.max(1, ...rows.map((row) => row.length), 1),
    [rows],
  );
  const columns = useMemo(
    () => Array.from({ length: colCount }, (_, index) => XLSX.utils.encode_col(index)),
    [colCount],
  );
  const headerRow = looksLikeHeaderRow(rows[0]);
  const selectedAddress = selected
    ? `${columns[selected.col] ?? "A"}${selected.row + 1}`
    : "A1";
  const selectedValue =
    selected != null ? (rows[selected.row]?.[selected.col] ?? "") : "";
  const accent = csv ? "teal" : "emerald";

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 bg-[#1e1e20] text-sm text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading {csv ? "CSV" : "spreadsheet"}…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-[#1e1e20] px-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <button
          type="button"
          disabled={downloading}
          onClick={async () => {
            setDownloading(true);
            try {
              await downloadArtifactFile(artifact, { allowSandbox: false });
            } finally {
              setDownloading(false);
            }
          }}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3.5 py-2 text-[13px] font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          Download original
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f3f3f3] text-zinc-800">
      <div
        className={cn(
          "flex shrink-0 items-center gap-3 border-b px-3 py-1.5",
          csv
            ? "border-teal-800/40 bg-[#0f766e] text-white"
            : "border-emerald-900/40 bg-[#217346] text-white",
        )}
      >
        <span className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide">
          {csv ? "CSV" : "XLSX"}
        </span>
        <span className="truncate text-[12px] font-medium">
          {artifact.title || (csv ? "Spreadsheet" : "Workbook")}
        </span>
        <span className="ml-auto hidden text-[11px] text-white/70 sm:inline">
          {rows.length.toLocaleString()} rows · {colCount} columns
        </span>
      </div>

      {truncated ? (
        <p className="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-[12px] text-amber-900">
          Showing the first {ROW_CAP.toLocaleString()} rows. Download the file to see
          everything.
        </p>
      ) : null}

      <div className="flex shrink-0 items-center gap-2 border-b border-zinc-200 bg-white px-2 py-1.5">
        <div
          className={cn(
            "w-14 shrink-0 rounded border bg-zinc-50 px-1.5 py-1 text-center font-mono text-[11px] font-semibold text-zinc-600",
            accent === "teal" ? "border-teal-200" : "border-emerald-200",
          )}
        >
          {selectedAddress}
        </div>
        <div className="min-w-0 flex-1 truncate rounded border border-zinc-200 bg-white px-2 py-1 text-[12px] text-zinc-700">
          {selectedValue || (
            <span className="text-zinc-400">Select a cell to inspect its value</span>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto custom-scrollbar bg-white">
        <table className="min-w-full border-collapse text-left text-[12px] tabular-nums">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="sticky left-0 z-20 w-10 min-w-10 border-b border-r border-zinc-200 bg-[#eef0f2] px-1 py-1.5 text-center text-[10px] font-medium text-zinc-400" />
              {columns.map((label, colIndex) => (
                <th
                  key={label}
                  className={cn(
                    "min-w-[6.5rem] border-b border-r border-zinc-200 bg-[#eef0f2] px-2 py-1.5 text-center text-[10px] font-semibold tracking-wide text-zinc-500",
                    selected?.col === colIndex &&
                      (csv ? "bg-teal-50 text-teal-800" : "bg-emerald-50 text-emerald-800"),
                  )}
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
                  className="px-4 py-16 text-center text-sm text-zinc-500"
                >
                  This sheet is empty.
                </td>
              </tr>
            ) : (
              rows.map((row, rowIndex) => {
                const isHeader = headerRow && rowIndex === 0;
                return (
                  <tr
                    key={rowIndex}
                    className={cn(
                      isHeader ? "bg-[#f7f8f9]" : "bg-white even:bg-[#fafafa]",
                    )}
                  >
                    <th
                      className={cn(
                        "sticky left-0 z-10 w-10 min-w-10 border-b border-r border-zinc-200 bg-[#eef0f2] px-1 py-1 text-center text-[10px] font-medium text-zinc-400",
                        selected?.row === rowIndex &&
                          (csv ? "bg-teal-50 text-teal-800" : "bg-emerald-50 text-emerald-800"),
                      )}
                    >
                      {rowIndex + 1}
                    </th>
                    {columns.map((_, colIndex) => {
                      const active =
                        selected?.row === rowIndex && selected?.col === colIndex;
                      return (
                        <td
                          key={colIndex}
                          onClick={() => setSelected({ row: rowIndex, col: colIndex })}
                          className={cn(
                            "max-w-[22rem] cursor-cell truncate border-b border-r border-zinc-200 px-2 py-1 text-zinc-800",
                            isHeader && "font-semibold text-zinc-900",
                            active &&
                              (csv
                                ? "bg-teal-50 ring-1 ring-inset ring-teal-500"
                                : "bg-emerald-50 ring-1 ring-inset ring-emerald-600"),
                          )}
                          title={row[colIndex] || undefined}
                        >
                          {row[colIndex] ?? ""}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {sheetNames.length > 0 ? (
        <div className="flex shrink-0 items-end gap-0 overflow-x-auto border-t border-zinc-200 bg-[#f3f3f3] px-1 pt-1">
          {sheetNames.map((name) => {
            const active = name === activeSheet;
            return (
              <button
                key={name}
                type="button"
                onClick={() => {
                  setActiveSheet(name);
                  setSelected(null);
                }}
                className={cn(
                  "relative -mb-px shrink-0 rounded-t-md border border-b-0 px-3 py-1.5 text-[12px] font-medium",
                  active
                    ? csv
                      ? "border-zinc-300 bg-white text-teal-800"
                      : "border-zinc-300 bg-white text-emerald-800"
                    : "border-transparent text-zinc-500 hover:bg-white/70 hover:text-zinc-800",
                )}
              >
                {name}
                {active ? (
                  <span
                    className={cn(
                      "absolute inset-x-0 -bottom-px h-0.5",
                      csv ? "bg-teal-600" : "bg-emerald-600",
                    )}
                  />
                ) : null}
              </button>
            );
          })}
          <div className="ml-auto hidden px-3 py-1.5 text-[11px] text-zinc-400 sm:block">
            Ready
          </div>
        </div>
      ) : null}
    </div>
  );
}
