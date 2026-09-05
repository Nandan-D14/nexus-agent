/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

export type SearchResult = {
  title: string;
  url: string;
  snippet: string;
};

/** CiteRef-compatible source without citation index (assigned at merge). */
export type SearchCiteRef = {
  label: string;
  host: string;
  url: string;
  /** Search snippet / summary for citation hover cards. */
  description?: string;
};

type ToolStepLike = {
  kind: string;
  tool?: string;
  result?: { output?: string; resultSummary?: Record<string, unknown> };
};

type EventSegmentLike = {
  kind: string;
  data?: { steps?: ToolStepLike[] };
};

const SEARCH_TOOLS = new Set([
  "search_web",
  "web_search",
  "scrape_web_page",
  "tavily_search",
]);

function stringValue(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

export function isSearchTool(tool: string): boolean {
  return SEARCH_TOOLS.has(tool);
}

export function normalizeSearchResults(values: unknown[]): SearchResult[] {
  return values
    .map((value) => {
      const item = objectValue(value);
      if (!item) return null;
      return {
        title: stringValue(item.title, item.name) ?? "",
        url: stringValue(item.url, item.href, item.link) ?? "",
        snippet:
          stringValue(item.snippet, item.body, item.description, item.summary) ??
          "",
      };
    })
    .filter((item): item is SearchResult => Boolean(item?.url || item?.title));
}

function resultsArrayFrom(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const obj = objectValue(value);
  if (!obj) return [];
  const nested = obj.results ?? obj.data ?? obj.items;
  return Array.isArray(nested) ? nested : [];
}

/**
 * Pull search results out of a normalized tool payload.
 *
 * The backend returns `{ status, summary, metadata: { results: [...] } }`, so
 * the hits live under `metadata`. Top-level keys are also accepted for
 * payloads that were flattened upstream.
 */
export function parseSearchToolResultSummary(
  tool: string,
  resultSummary?: Record<string, unknown> | null,
): SearchResult[] | null {
  if (!isSearchTool(tool) || !resultSummary) return null;

  const candidates = [
    objectValue(resultSummary.metadata),
    resultSummary,
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    const values = resultsArrayFrom(candidate);
    if (values.length === 0) continue;
    const results = normalizeSearchResults(values);
    if (results.length > 0) return results;
  }
  return null;
}

/**
 * Parse tool output for web-search style tools.
 * Supports a plain JSON array or `{ results: [...] }` (tavily shape).
 */
export function parseSearchToolOutput(
  tool: string,
  output?: string | null,
): SearchResult[] | null {
  if (!isSearchTool(tool) || !output?.trim()) return null;

  try {
    const values = resultsArrayFrom(JSON.parse(output));
    if (values.length === 0) return null;
    const results = normalizeSearchResults(values);
    return results.length > 0 ? results : null;
  } catch {
    return null;
  }
}

/**
 * Resolve search results from whichever channel carried them: the structured
 * `result_summary` (normal case) or a JSON `output` string (legacy / replay).
 */
export function resolveSearchResults(
  tool: string,
  options: {
    output?: string | null;
    resultSummary?: Record<string, unknown> | null;
  },
): SearchResult[] | null {
  return (
    parseSearchToolResultSummary(tool, options.resultSummary) ??
    parseSearchToolOutput(tool, options.output)
  );
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/**
 * Walk turn eventSegments / task groups for search tool outputs and
 * return unique CiteRef-compatible refs (deduped by URL, first-seen order).
 */
export function collectSearchRefsFromEventSegments(
  segments: EventSegmentLike[],
): SearchCiteRef[] {
  const seen = new Set<string>();
  const refs: SearchCiteRef[] = [];

  for (const seg of segments) {
    if (seg.kind !== "task_group") continue;
    const steps = seg.data?.steps;
    if (!steps) continue;

    for (const step of steps) {
      if (step.kind !== "tool_invocation" || !step.tool) continue;
      const results = resolveSearchResults(step.tool, {
        output: step.result?.output,
        resultSummary: step.result?.resultSummary,
      });
      if (!results) continue;

      for (const result of results) {
        if (!result.url || seen.has(result.url)) continue;
        seen.add(result.url);
        refs.push({
          label: result.title || hostname(result.url),
          host: hostname(result.url),
          url: result.url,
          description: result.snippet.trim() || undefined,
        });
      }
    }
  }

  return refs;
}
