import type { LifecycleStage } from "./types";

export const LIFECYCLE_STAGE_LABEL: Record<LifecycleStage, string> = {
  new_lead: "New lead",
  contacted: "Contacted",
  engaged: "Engaged",
  pre_app: "Pre-application",
  pre_approved: "Pre-approved",
  shopping: "Shopping",
  under_contract: "Under contract",
  in_processing: "In processing",
  in_underwriting: "In underwriting",
  clear_to_close: "Clear to close",
  closed_active: "Closed · active",
  closed_past_client: "Past client",
  dead: "Dead",
};

export const LIFECYCLE_STAGE_ORDER: LifecycleStage[] = [
  "new_lead",
  "contacted",
  "engaged",
  "pre_app",
  "pre_approved",
  "shopping",
  "under_contract",
  "in_processing",
  "in_underwriting",
  "clear_to_close",
  "closed_active",
  "closed_past_client",
  "dead",
];

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();

  if (sameDay(date, today)) return "Today";
  if (sameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

export function dayKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}
