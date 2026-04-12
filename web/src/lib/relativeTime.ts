/**
 * Format a timestamp as a short relative duration ("just now", "2s ago",
 * "3m ago", "2h ago", "4d ago", "12 Apr"). Pure; safe for render.
 */
export function formatRelative(
  isoTimestamp: string | undefined,
  now: number = Date.now(),
): string {
  if (!isoTimestamp) return "—";
  const then = new Date(isoTimestamp).getTime();
  if (Number.isNaN(then)) return "—";
  const deltaSec = Math.max(0, Math.floor((now - then) / 1000));
  if (deltaSec < 3) return "just now";
  if (deltaSec < 60) return `${deltaSec}s ago`;
  const m = Math.floor(deltaSec / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  // Fallback to a compact date
  const date = new Date(isoTimestamp);
  const dd = date.getDate();
  const mon = date.toLocaleString(undefined, { month: "short" });
  return `${dd} ${mon}`;
}
