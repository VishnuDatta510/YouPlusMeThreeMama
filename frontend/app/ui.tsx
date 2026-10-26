import type { PicoType, RunLog, Status } from "@/lib/api";
import { SOURCE_NAMES } from "@/lib/api";

/** sessionStorage key: the record ids of the list last shown, for next/previous on a record page. */
export const QUEUE_KEY = "mr_queue";
/** sessionStorage key: the filters of that list, so a record page links back to it. */
export const LIST_KEY = "mr_list";

export const STATUS: Record<Status, { label: string; className: string; bar: string }> = {
  include: { label: "Included", className: "bg-inc-bg text-inc", bar: "bg-inc" },
  maybe: { label: "Maybe", className: "bg-may-bg text-may", bar: "bg-may" },
  exclude: { label: "Excluded", className: "bg-exc-bg text-exc", bar: "bg-exc" },
  unscreened: { label: "Unscreened", className: "bg-uns-bg text-uns", bar: "bg-faint/40" },
};

export function StatusBadge({ status, className = "" }: { status: Status; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS[status].className} ${className}`}
    >
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {STATUS[status].label}
    </span>
  );
}

export const PICO: Record<PicoType, { label: string }> = {
  P: { label: "Population" },
  I: { label: "Intervention" },
  C: { label: "Comparator" },
  O: { label: "Outcome" },
};

export function Logo({ className = "size-6" }: { className?: string }) {
  // A funnel of records narrowing to the included few.
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <rect x="2" y="3" width="20" height="3.2" rx="1.6" className="fill-accent/35" />
      <rect x="5" y="9" width="14" height="3.2" rx="1.6" className="fill-accent/65" />
      <rect x="8.5" y="15" width="7" height="3.2" rx="1.6" className="fill-accent" />
      <circle cx="12" cy="21.4" r="1.6" className="fill-inc" />
    </svg>
  );
}

export function PageHeader({
  title,
  children,
  actions,
}: {
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="font-serif text-[2rem] leading-tight font-semibold tracking-tight">{title}</h1>
        {children && <p className="mt-2 text-[15px] leading-relaxed text-muted">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="rounded-lg border border-exc/30 bg-exc-bg px-3 py-2 text-sm text-exc">
      {children}
    </p>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        checked ? "bg-accent" : "bg-rule"
      }`}
    >
      <span
        className={`size-4 rounded-full bg-surface shadow-sm transition-transform ${
          checked ? "translate-x-4.5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export function Spinner() {
  return (
    <span
      className="inline-block size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent"
      aria-hidden
    />
  );
}

const STEP_NAMES: Record<string, string> = {
  fetch: "Fetch",
  dedupe: "Deduplicate",
  screen: "Screen",
  pico: "Tag PICO",
};

const humanize = (k: string) => k.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

/** The figures a step reported, as label/value pairs (nested counts such as per-source hits are flattened). */
export function stepFacts(details: Record<string, unknown>): [string, string][] {
  return Object.entries(details).flatMap(([k, v]): [string, string][] => {
    if (v && typeof v === "object")
      return Object.entries(v as Record<string, unknown>).map(([s, n]) => [SOURCE_NAMES[s] ?? s, String(n)]);
    if (k === "method_version") {
      const [method, criteria] = String(v).split(":");
      const n = criteria ? criteria.split(",").length : 0;
      return [["Method", criteria === undefined ? method : `${method}, ${n} criteria`]];
    }
    return [[humanize(k), typeof v === "number" ? v.toLocaleString() : String(v)]];
  });
}

/** One pipeline run shown as its steps in order, each with the figures it reported. */
export function RunSteps({ logs }: { logs: RunLog[] }) {
  return (
    <ol
      className={`grid gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-2 ${
        logs.length > 2 ? "lg:grid-cols-4" : ""
      }`}
    >
      {logs.map((l, i) => (
        <li key={l.id ?? i} className="bg-surface p-3.5">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            <span
              className={`flex size-5 items-center justify-center rounded-full text-[11px] font-semibold ${
                l.status === "ok" ? "bg-inc-bg text-inc" : l.status === "error" ? "bg-exc-bg text-exc" : "bg-uns-bg"
              }`}
            >
              {i + 1}
            </span>
            {STEP_NAMES[l.step] ?? humanize(l.step)}
            {l.status === "error" && <span className="text-xs font-normal text-exc">failed</span>}
          </div>
          {l.status === "error" ? (
            <p className="text-xs wrap-break-word text-exc">{String(l.details.error ?? "Unknown error")}</p>
          ) : (
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
              {stepFacts(l.details).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{k}</dt>
                  <dd className="text-right font-medium wrap-break-word tabular-nums">{v}</dd>
                </div>
              ))}
            </dl>
          )}
        </li>
      ))}
    </ol>
  );
}
