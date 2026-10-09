export const number = (v: number | null | undefined) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        notation: v >= 10000 ? "compact" : "standard",
        maximumFractionDigits: 1,
      }).format(v);
export const money = (v: number | null | undefined) =>
  v == null ? "Unavailable" : `$${v.toFixed(v < 0.01 && v > 0 ? 4 : 2)}`;
export const duration = (v: number | null | undefined) =>
  v == null
    ? "—"
    : v < 1000
      ? `${Math.round(v)}ms`
      : v < 60000
        ? `${(v / 1000).toFixed(2)}s`
        : `${(v / 60000).toFixed(1)}m`;
export const time = (v: string) =>
  new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const date = (v: string) =>
  new Date(v).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const label = (v: string) => v.toLowerCase().replaceAll("_", " ");
export function relative(v: string) {
  const mins = Math.max(
    0,
    Math.floor((Date.now() - new Date(v).getTime()) / 60000),
  );
  return mins === 0
    ? "Just now"
    : mins < 60
      ? `${mins}m ago`
      : mins < 1440
        ? `${Math.floor(mins / 60)}h ago`
        : `${Math.floor(mins / 1440)}d ago`;
}
export function spanDepth(
  span: { span_id: string; parent_span_id?: string },
  spans: { span_id: string; parent_span_id?: string }[],
) {
  const seen = new Set([span.span_id]);
  let parent = span.parent_span_id,
    depth = 0;
  while (parent && !seen.has(parent)) {
    seen.add(parent);
    const found = spans.find((s) => s.span_id === parent);
    if (!found) break;
    depth++;
    parent = found.parent_span_id;
  }
  return Math.min(depth, 16);
}
