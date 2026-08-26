const DAY_MS = 24 * 60 * 60 * 1000;

export function formatDateGroup(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const delta = startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  if (delta <= 0) return "Today";
  if (delta <= DAY_MS) return "Yesterday";
  if (delta <= 7 * DAY_MS) return "Previous 7 days";
  if (delta <= 30 * DAY_MS) return "Previous 30 days";
  return date.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return "<1s";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
