/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
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
};

type ToolStepLike = {
  kind: string;
  tool?: string;
  result?: { output?: string };
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
    const parsed: unknown = JSON.parse(output);
    let values: unknown[] = [];

    if (Array.isArray(parsed)) {
      values = parsed;
    } else {
      const obj = objectValue(parsed);
      if (obj) {
        const nested = obj.results ?? obj.data ?? obj.items;
        if (Array.isArray(nested)) values = nested;
      }
    }

    if (values.length === 0) return null;
    const results = normalizeSearchResults(values);
    return results.length > 0 ? results : null;
  } catch {
    return null;
  }
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
      const results = parseSearchToolOutput(step.tool, step.result?.output);
      if (!results) continue;

      for (const result of results) {
        if (!result.url || seen.has(result.url)) continue;
        seen.add(result.url);
        refs.push({
          label: result.title || hostname(result.url),
          host: hostname(result.url),
          url: result.url,
        });
      }
    }
  }

  return refs;
}
