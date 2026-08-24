/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Download,
  File,
  Folder,
  FolderOpen,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { authenticatedFetch, readApiError } from "@/lib/api-client";

export type SandboxFileEntry = {
  name: string;
  relative_path: string;
  is_dir: boolean;
  size: number;
};

type TreeResponse = {
  workspace_path: string;
  relative_path: string;
  entries: SandboxFileEntry[];
};

type TreeNode = {
  name: string;
  relative_path: string;
  is_dir: boolean;
  size: number;
  children: TreeNode[];
};

type Props = {
  sessionId: string | null | undefined;
  active?: boolean;
};

function formatBytes(size: number): string {
  if (!size || size < 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function buildTree(entries: SandboxFileEntry[]): TreeNode[] {
  const root: TreeNode[] = [];
  const dirMap = new Map<string, TreeNode>();

  const ensureDir = (relativePath: string, name: string): TreeNode => {
    const existing = dirMap.get(relativePath);
    if (existing) return existing;
    const node: TreeNode = {
      name,
      relative_path: relativePath,
      is_dir: true,
      size: 0,
      children: [],
    };
    dirMap.set(relativePath, node);
    const parentPath = relativePath.includes("/")
      ? relativePath.slice(0, relativePath.lastIndexOf("/"))
      : "";
    if (!parentPath) {
      root.push(node);
    } else {
      const parentName = parentPath.includes("/")
        ? parentPath.slice(parentPath.lastIndexOf("/") + 1)
        : parentPath;
      ensureDir(parentPath, parentName).children.push(node);
    }
    return node;
  };

  const sorted = [...entries].sort((a, b) =>
    a.relative_path.localeCompare(b.relative_path),
  );

  for (const entry of sorted) {
    const parentPath = entry.relative_path.includes("/")
      ? entry.relative_path.slice(0, entry.relative_path.lastIndexOf("/"))
      : "";
    if (parentPath) {
      const parentName = parentPath.includes("/")
        ? parentPath.slice(parentPath.lastIndexOf("/") + 1)
        : parentPath;
      ensureDir(parentPath, parentName);
    }

    if (entry.is_dir) {
      ensureDir(entry.relative_path, entry.name);
      continue;
    }

    const fileNode: TreeNode = {
      name: entry.name,
      relative_path: entry.relative_path,
      is_dir: false,
      size: entry.size,
      children: [],
    };
    if (!parentPath) {
      root.push(fileNode);
    } else {
      ensureDir(
        parentPath,
        parentPath.includes("/")
          ? parentPath.slice(parentPath.lastIndexOf("/") + 1)
          : parentPath,
      ).children.push(fileNode);
    }
  }

  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
    nodes.forEach((n) => {
      if (n.children.length) sortNodes(n.children);
    });
  };
  sortNodes(root);
  return root;
}

function TreeRow({
  node,
  depth,
  expanded,
  onToggle,
  downloadingPath,
  onDownload,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  downloadingPath: string | null;
  onDownload: (path: string, name: string) => void;
}) {
  const isOpen = expanded.has(node.relative_path);
  const isDownloading = downloadingPath === node.relative_path;

  return (
    <div>
      <div
        className="group flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800/60"
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {node.is_dir ? (
          <button
            type="button"
            onClick={() => onToggle(node.relative_path)}
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
          >
            {isOpen ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
            )}
            {isOpen ? (
              <FolderOpen className="h-4 w-4 shrink-0 text-amber-400/90" />
            ) : (
              <Folder className="h-4 w-4 shrink-0 text-amber-400/90" />
            )}
            <span className="truncate font-medium text-zinc-200">{node.name}</span>
          </button>
        ) : (
          <>
            <span className="inline-flex w-3.5 shrink-0" />
            <File className="h-4 w-4 shrink-0 text-zinc-500" />
            <span className="min-w-0 flex-1 truncate">{node.name}</span>
            {node.size > 0 && (
              <span className="shrink-0 text-[10px] text-zinc-600">
                {formatBytes(node.size)}
              </span>
            )}
            <button
              type="button"
              onClick={() => onDownload(node.relative_path, node.name)}
              disabled={isDownloading}
              className="shrink-0 rounded p-1 text-zinc-500 opacity-0 transition-opacity hover:bg-zinc-700 hover:text-zinc-200 group-hover:opacity-100 disabled:opacity-50"
              aria-label={`Download ${node.name}`}
            >
              {isDownloading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
            </button>
          </>
        )}
      </div>
      {node.is_dir && isOpen &&
        node.children.map((child) => (
          <TreeRow
            key={child.relative_path}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
            downloadingPath={downloadingPath}
            onDownload={onDownload}
          />
        ))}
    </div>
  );
}

export function SandboxFilesPanel({ sessionId, active = true }: Props) {
  const [entries, setEntries] = useState<SandboxFileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [downloadingPath, setDownloadingPath] = useState<string | null>(null);

  const tree = useMemo(() => buildTree(entries), [entries]);

  const loadTree = useCallback(async () => {
    if (!sessionId) {
      setEntries([]);
      setError("No active session.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/files/tree`,
      );
      if (!res.ok) {
        const apiError = await readApiError(res);
        if (res.status === 410) {
          setError("Sandbox is not active. Start or reconnect the session to browse files.");
        } else {
          setError(apiError.message || `Failed to list files (${res.status})`);
        }
        setEntries([]);
        return;
      }
      const body = (await res.json()) as TreeResponse;
      const next = Array.isArray(body.entries) ? body.entries : [];
      setEntries(next);
      // Expand top-level directories by default
      setExpanded(
        new Set(
          next
            .filter((e) => e.is_dir && !e.relative_path.includes("/"))
            .map((e) => e.relative_path),
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to list workspace files");
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!active) return;
    void loadTree();
  }, [active, loadTree]);

  const onToggle = useCallback((path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const onDownload = useCallback(
    async (relativePath: string, name: string) => {
      if (!sessionId) return;
      setDownloadingPath(relativePath);
      try {
        const res = await authenticatedFetch(
          `/api/v1/sessions/${encodeURIComponent(sessionId)}/files/download?relative_path=${encodeURIComponent(relativePath)}`,
        );
        if (!res.ok) {
          const apiError = await readApiError(res);
          setError(apiError.message || "Download failed");
          return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = name || "download.bin";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Download failed");
      } finally {
        setDownloadingPath(null);
      }
    },
    [sessionId],
  );

  const fileCount = entries.filter((e) => !e.is_dir).length;

  return (
    <div className="flex h-full flex-col bg-[#0a0a0c]">
      <div className="flex items-center justify-between border-b border-zinc-800/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <Folder className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-zinc-100">Sandbox Files</h3>
          {!loading && entries.length > 0 && (
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              {fileCount} file{fileCount === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => void loadTree()}
          disabled={loading || !sessionId}
          className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/60 px-2 py-1 text-[11px] font-medium text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-200 disabled:opacity-40"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto px-2 py-2">
        {loading && entries.length === 0 ? (
          <div className="flex h-full min-h-[200px] items-center justify-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading workspace files…
          </div>
        ) : error ? (
          <div className="flex h-full min-h-[200px] items-center justify-center px-4">
            <div className="w-full max-w-md rounded-xl border border-dashed border-zinc-800 bg-white/5 px-4 py-8 text-center text-sm text-zinc-500">
              {error}
            </div>
          </div>
        ) : tree.length === 0 ? (
          <div className="flex h-full min-h-[200px] items-center justify-center px-4">
            <div className="flex w-full max-w-md flex-col items-center gap-3 rounded-xl border border-dashed border-zinc-800 bg-white/5 px-4 py-8 text-center text-sm text-zinc-500">
              <Folder className="h-8 w-8 opacity-20" />
              <p>No files in the run workspace yet.</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col">
            {tree.map((node) => (
              <TreeRow
                key={node.relative_path}
                node={node}
                depth={0}
                expanded={expanded}
                onToggle={onToggle}
                downloadingPath={downloadingPath}
                onDownload={onDownload}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
