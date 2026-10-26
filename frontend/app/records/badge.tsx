import type { PicoType, RecordRow } from "@/lib/api";

const STATUS_STYLES: Record<RecordRow["status"], string> = {
  include: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  exclude: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  maybe: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  unscreened: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
};

export function StatusBadge({ status }: { status: RecordRow["status"] }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[status]}`}>{status}</span>
  );
}

export const PICO: Record<PicoType, { label: string; className: string }> = {
  P: { label: "Population", className: "bg-sky-200 dark:bg-sky-800/60" },
  I: { label: "Intervention", className: "bg-lime-200 dark:bg-lime-800/60" },
  C: { label: "Comparator", className: "bg-amber-200 dark:bg-amber-800/60" },
  O: { label: "Outcome", className: "bg-fuchsia-200 dark:bg-fuchsia-800/60" },
};
