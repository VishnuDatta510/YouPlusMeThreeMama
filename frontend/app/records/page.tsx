"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { api, SOURCE_NAMES, type QueryVersion, type RecordRow, type Status } from "@/lib/api";
import { ErrorNote, PageHeader, LIST_KEY, QUEUE_KEY, Spinner, STATUS, StatusBadge } from "../ui";

const ORDER: Status[] = ["include", "maybe", "exclude", "unscreened"];
const param = (v: string | string[] | undefined) => (typeof v === "string" ? v : "");

export default function RecordsPage({ searchParams }: PageProps<"/records">) {
  const initial = use(searchParams);
  const [version, setVersion] = useState(param(initial.version));
  const [status, setStatus] = useState(param(initial.status));
  const [review, setReview] = useState(param(initial.review) === "1");
  const [conflict, setConflict] = useState(param(initial.conflict) === "1");
  const [text, setText] = useState(param(initial.q));
  const [versions, setVersions] = useState<QueryVersion[]>([]);
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api.versions().then(setVersions).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    api
      .records({ query_version_id: version, needs_review: review ? "true" : "", conflict: conflict ? "true" : "" })
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [version, review, conflict]);

  // Filters live in the URL so the back button from a record returns to the same list.
  useEffect(() => {
    const qs = new URLSearchParams(
      Object.entries({ version, status, review: review ? "1" : "", conflict: conflict ? "1" : "", q: text }).filter(
        ([, v]) => v,
      ),
    );
    window.history.replaceState(null, "", qs.size ? `?${qs}` : window.location.pathname);
    try {
      sessionStorage.setItem(LIST_KEY, qs.size ? `?${qs}` : "");
    } catch {}
  }, [version, status, review, conflict, text]);

  const matching = useMemo(() => {
    const needle = text.trim().toLowerCase();
    if (!rows || !needle) return rows ?? [];
    return rows.filter((r) =>
      [r.title, r.first_author, r.journal, r.pmid, r.doi].some((f) => f?.toLowerCase().includes(needle)),
    );
  }, [rows, text]);
  const shown = useMemo(() => (status ? matching.filter((r) => r.status === status) : matching), [matching, status]);

  useEffect(() => {
    try {
      sessionStorage.setItem(QUEUE_KEY, JSON.stringify(shown.map((r) => r.id)));
    } catch {}
  }, [shown]);

  const fetched = versions.filter((v) => v.status === "fetched");
  const current = versions.find((v) => String(v.id) === version);

  return (
    <div>
      <PageHeader
        title="Records"
        actions={
          <button
            className="btn"
            disabled={exporting}
            onClick={() => {
              setExporting(true);
              api
                .downloadIncludedCsv(version)
                .catch((e) => setError(e.message))
                .finally(() => setExporting(false));
            }}
          >
            {exporting ? (
              <Spinner />
            ) : (
              <svg viewBox="0 0 16 16" className="size-4 fill-none stroke-current stroke-[1.5]" aria-hidden>
                <path d="M8 2.5v7M5 6.5l3 3 3-3M3 11.5v2h10v-2" />
              </svg>
            )}
            Export included as CSV
          </button>
        }
      >
        {current
          ? `The records v${current.version_number} found. Each row is one study; its duplicates are folded into it.`
          : "Your working set. Each row is one study; its duplicates are folded into it and hidden, never deleted."}
      </PageHeader>

      <ErrorNote>{error}</ErrorNote>

      {rows && <Ledger rows={matching} status={status} onStatus={setStatus} />}

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <div className="relative min-w-60 flex-1">
          <svg
            viewBox="0 0 16 16"
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 fill-none stroke-faint stroke-[1.5]"
            aria-hidden
          >
            <circle cx="7" cy="7" r="4.5" />
            <path d="m10.5 10.5 3 3" />
          </svg>
          <input
            className="input w-full pl-9"
            type="search"
            placeholder="Filter by title, author, journal, PMID or DOI"
            aria-label="Filter records"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <select
          className="input"
          aria-label="Query version"
          value={version}
          onChange={(e) => setVersion(e.target.value)}
        >
          <option value="">Working set</option>
          {fetched.map((v) => (
            <option key={v.id} value={v.id}>
              v{v.version_number}: {v.query_string.slice(0, 40)}
            </option>
          ))}
        </select>
        <Toggle on={review} onChange={setReview}>
          Possible duplicates
        </Toggle>
        <Toggle on={conflict} onChange={setConflict}>
          Reviewer conflicts
        </Toggle>
      </div>

      <div className="panel mt-4 overflow-hidden">
        {rows === null ? (
          <p className="px-5 py-10 text-center text-sm text-muted">Loading records</p>
        ) : shown.length === 0 ? (
          <div className="px-5 py-14 text-center">
            {rows.length === 0 && !review && !conflict ? (
              <>
                <p className="font-serif text-lg">Nothing to screen yet</p>
                <p className="mt-1 text-sm text-muted">
                  Fetch a search on the{" "}
                  <Link className="link" href="/">
                    Searches
                  </Link>{" "}
                  page and its records appear here.
                </p>
              </>
            ) : (
              <>
                <p className="font-serif text-lg">No records match these filters</p>
                <button
                  className="btn mt-3"
                  onClick={() => {
                    setStatus("");
                    setText("");
                    setReview(false);
                    setConflict(false);
                  }}
                >
                  Clear filters
                </button>
              </>
            )}
          </div>
        ) : (
          <ul className="divide-y divide-rule">
            {shown.map((r) => (
              <Row key={r.id} r={r} />
            ))}
          </ul>
        )}
      </div>
      {rows && shown.length > 0 && (
        <p className="mt-3 text-xs text-faint">
          {shown.length.toLocaleString()} of {rows.length.toLocaleString()} studies shown
        </p>
      )}
    </div>
  );
}

function Toggle({ on, onChange, children }: { on: boolean; onChange: (v: boolean) => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onChange(!on)}
      className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
        on ? "border-accent/60 bg-accent-soft text-ink" : "border-rule bg-surface text-muted hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

/** How the studies split across decisions; each part filters the list. */
function Ledger({ rows, status, onStatus }: { rows: RecordRow[]; status: string; onStatus: (s: string) => void }) {
  const counts = Object.fromEntries(ORDER.map((s) => [s, rows.filter((r) => r.status === s).length])) as Record<
    Status,
    number
  >;
  const total = rows.length;
  if (total === 0) return null;
  return (
    <section aria-label="Screening progress" className="panel p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-serif text-lg">
          <span className="text-2xl font-semibold tabular-nums">{total.toLocaleString()}</span> studies
        </p>
        <p className="text-sm text-muted">
          {Math.round(((total - counts.unscreened) / total) * 100)}% have a decision
        </p>
      </div>
      <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full">
        {ORDER.filter((s) => counts[s]).map((s) => (
          <button
            key={s}
            aria-label={`Show ${STATUS[s].label.toLowerCase()} only`}
            onClick={() => onStatus(status === s ? "" : s)}
            className={`h-full transition-opacity ${STATUS[s].bar} ${status && status !== s ? "opacity-25" : ""}`}
            style={{ width: `${(counts[s] / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={() => onStatus("")}
          className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${!status ? "bg-uns-bg font-medium" : "text-muted hover:text-ink"}`}
        >
          All
        </button>
        {ORDER.map((s) => (
          <button
            key={s}
            aria-pressed={status === s}
            onClick={() => onStatus(status === s ? "" : s)}
            className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors ${
              status === s ? `${STATUS[s].className} font-medium` : "text-muted hover:text-ink"
            }`}
          >
            <span className={`size-2 rounded-full ${STATUS[s].bar}`} aria-hidden />
            {STATUS[s].label}
            <span className="tabular-nums">{counts[s].toLocaleString()}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function Row({ r }: { r: RecordRow }) {
  const meta = [r.first_author, r.journal, r.year].filter(Boolean).join(", ");
  return (
    <li>
      <Link
        href={`/records/${r.id}`}
        className="grid gap-x-6 gap-y-2 px-5 py-4 transition-colors hover:bg-paper focus-visible:bg-paper md:grid-cols-[minmax(0,1fr)_15rem]"
      >
        <div className="min-w-0">
          <p className="font-serif text-[16px] leading-snug">{r.title || "Untitled record"}</p>
          <p className="mt-1 truncate text-[13px] text-muted">
            {meta}
            {r.pmid && <span className="text-faint"> PMID {r.pmid}</span>}
          </p>
          {(r.duplicates > 0 || r.needs_review || r.conflict || r.origin !== "pubmed") && (
            <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
              {r.conflict && (
                <span className="rounded-md bg-exc-bg px-2 py-0.5 font-medium text-exc">Reviewers disagree</span>
              )}
              {r.needs_review && (
                <span className="rounded-md bg-may-bg px-2 py-0.5 font-medium text-may">Possible duplicate to check</span>
              )}
              {r.duplicates > 0 && (
                <span className="rounded-md bg-uns-bg px-2 py-0.5 text-muted">
                  {r.duplicates} {r.duplicates === 1 ? "duplicate" : "duplicates"} folded in
                </span>
              )}
              {r.origin !== "pubmed" && (
                <span className="rounded-md border border-rule px-2 py-0.5 text-muted">
                  {SOURCE_NAMES[r.origin] ?? r.origin}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-col items-start gap-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={r.status} />
            {r.source && <span className="text-xs text-faint">{r.source === "human" ? "Reviewer" : "Machine"}</span>}
          </div>
          {/* a machine include has no reason worth reading on every row */}
          {r.reason && !(r.source === "machine" && r.status === "include") && (
            <p className="line-clamp-2 text-[13px] text-muted">{r.reason}</p>
          )}
        </div>
      </Link>
    </li>
  );
}
