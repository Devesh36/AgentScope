export const RUN_STATUSES = ["running", "completed", "failed", "paused", "cancelled"];
export const INCIDENT_STATUSES = ["active", "OPEN", "INVESTIGATING", "ACTION_REQUIRED", "VERIFYING", "RESOLVED", "DISMISSED"];
export const PAGE_SIZE = 20;

export function updateView(values: Record<string, string | null>, replace = false) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === "") url.searchParams.delete(key);
    else url.searchParams.set(key, value);
  }
  if (url.href !== window.location.href) {
    window.history[replace ? "replaceState" : "pushState"](null, "", url.pathname + url.search + url.hash);
  }
}

export function choice(value: string | null, allowed: readonly string[], fallback: string) {
  return value && allowed.includes(value) ? value : fallback;
}

export function readExplorerFilters(params: { get: (key: string) => string | null }, kind: "runs" | "incidents") {
  const rawPage = params.get("page") || "1";
  const page = /^\d+$/.test(rawPage) && Number(rawPage) >= 1 && Number(rawPage) <= 1_000_000 ? Number(rawPage) : 1;
  return {
    search: (params.get("q") || "").slice(0, 200),
    status: choice(params.get("status"), ["all", ...(kind === "runs" ? RUN_STATUSES : INCIDENT_STATUSES)], kind === "runs" ? "all" : "active"),
    severity: choice(params.get("severity"), ["all", "critical", "high", "medium", "low"], "all"),
    sort: choice(params.get("sort"), ["newest", "oldest"], "newest"),
    offset: (page - 1) * PAGE_SIZE,
  };
}

// Only supported view parameters belong in a shared link. Never copy arbitrary
// query parameters, which could contain credentials or third-party data.
export function viewLink(href: string, project: string, hours: number, source: string, kind: "runs" | "incidents") {
  const url = new URL(href);
  const filters = readExplorerFilters(url.searchParams, kind);
  const params = new URLSearchParams({ project });
  if (filters.search) params.set("q", filters.search);
  params.set("status", filters.status);
  if (filters.offset) params.set("page", String(filters.offset / PAGE_SIZE + 1));
  if (kind === "runs") {
    params.set("hours", String(hours));
    params.set("source", source);
  } else {
    params.set("severity", filters.severity);
    params.set("sort", filters.sort);
  }
  url.search = params.toString();
  url.hash = "";
  url.username = "";
  url.password = "";
  return url.toString();
}
