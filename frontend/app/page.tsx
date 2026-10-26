"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  SOURCE_NAMES,
  type QueryIn,
  type QueryVersion,
  type RecordBrief,
  type Revert,
  type RunLog,
  type Source,
  type VersionDiff,
} from "@/lib/api";
import { ErrorNote, PageHeader, RunSteps, Spinner, StatusBadge, stepFacts, Switch } from "./ui";

type Panel =
  | { id: number; kind: "run"; title: string; logs: RunLog[] }
  | { id: number; kind: "history"; logs: RunLog[] }
  | { id: number; kind: "diff" }
  | { id: number; kind: "revert"; data: Revert };

const fmtDate = (d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const fmtTime = (d: string) =>
  new Date(d).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function SearchesPage() {
  const [versions, setVersions] = useState<QueryVersion[] | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [editing, setEditing] = useState<QueryVersion | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const composer = useRef<HTMLDivElement>(null);

  const load = useCallback(() => api.versions().then(setVersions).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    setError("");
    try {
      await fn();
      await load();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(null);
    }
  }

  const byId = new Map((versions ?? []).map((v) => [v.id, v]));
  const rootOf = (v: QueryVersion): number => {
    let cur = v;
    while (cur.parent_version_id && byId.has(cur.parent_version_id)) cur = byId.get(cur.parent_version_id)!;
    return cur.id;
  };
  const active = (versions ?? []).filter((v) => v.active);

  return (
    <div>
      <PageHeader
        title="Searches"
        actions={
          <ImportButton
            busy={busy !== null}
            onImport={(name, text) =>
              run("import", async () => {
                const logs = await api.importSnapshot(name, text);
                setPanel({ id: logs[0].query_version_id, kind: "run", title: `Imported ${name}`, logs });
              })
            }
          />
        }
      >
        Write a query and count its hits; nothing is downloaded until you fetch. Every edit is saved as a new
        version, and the records of the versions in your working set are deduplicated and screened together.
      </PageHeader>

      <div ref={composer} className="scroll-mt-20">
        <Composer
          key={editing?.id ?? "new"}
          editing={editing}
          busy={busy === "preview"}
          disabled={busy !== null}
          onCancel={() => setEditing(null)}
          onSubmit={(q) =>
            run("preview", async () => {
              await api.preview(q);
              setEditing(null);
            })
          }
        />
      </div>

      <div className="mt-6">
        <ErrorNote>{error}</ErrorNote>
      </div>

      <section className="mt-10">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-serif text-xl font-semibold">Versions</h2>
          {versions && versions.length > 0 && (
            <p className="text-sm text-muted">
              {active.length === 0
                ? "No version is in the working set yet."
                : `Working set: ${active.map((v) => `v${v.version_number}`).join(", ")}`}
            </p>
          )}
        </div>

        {versions === null ? (
          <p className="text-sm text-muted">Loading versions</p>
        ) : versions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-rule px-6 py-12 text-center">
            <p className="font-serif text-lg">No searches yet</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted">
              Write a query above and count its hits, or import a PubMed XML or Europe PMC JSON file you saved
              earlier.
            </p>
          </div>
        ) : (
          <ol>
            {versions.map((v, i) => {
              const lineage = versions.filter((o) => rootOf(o) === rootOf(v));
              const canRevert =
                v.status === "fetched" && (!v.active || lineage.some((o) => o.id !== v.id && o.active));
              return (
                <VersionItem
                  key={v.id}
                  v={v}
                  last={i === versions.length - 1}
                  parent={v.parent_version_id ? byId.get(v.parent_version_id) : undefined}
                  others={versions.filter((o) => o.id !== v.id && o.status === "fetched")}
                  canRevert={canRevert}
                  busy={busy}
                  panel={panel?.id === v.id ? panel : null}
                  onClose={() => setPanel(null)}
                  onFetch={() =>
                    run(`fetch-${v.id}`, async () =>
                      setPanel({ id: v.id, kind: "run", title: "Fetch and screen", logs: await api.runPipeline(v.id) }),
                    )
                  }
                  onToggle={(on) =>
                    run(`toggle-${v.id}`, async () =>
                      setPanel({
                        id: v.id,
                        kind: "run",
                        title: on ? "Added to the working set" : "Taken out of the working set",
                        logs: await api.setActive(v.id, on),
                      }),
                    )
                  }
                  onRevert={() =>
                    run(`revert-${v.id}`, async () =>
                      setPanel({ id: v.id, kind: "revert", data: await api.revert(v.id) }),
                    )
                  }
                  onHistory={() =>
                    run(`history-${v.id}`, async () =>
                      setPanel({ id: v.id, kind: "history", logs: await api.runs(v.id) }),
                    )
                  }
                  onDiff={() => setPanel({ id: v.id, kind: "diff" })}
                  onEdit={() => {
                    setEditing(v);
                    composer.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                />
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}

function Composer({
  editing,
  busy,
  disabled,
  onSubmit,
  onCancel,
}: {
  editing: QueryVersion | null;
  busy: boolean;
  disabled: boolean;
  onSubmit: (q: QueryIn) => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState(editing?.query_string ?? "");
  const [dateFrom, setDateFrom] = useState(editing?.date_from ?? "");
  const [dateTo, setDateTo] = useState(editing?.date_to ?? "");
  const [sources, setSources] = useState<Source[]>(
    (editing?.sources.filter((s) => s === "pubmed" || s === "europepmc") as Source[] | undefined) ?? ["pubmed"],
  );
  const toggle = (s: Source) =>
    setSources(sources.includes(s) ? sources.filter((x) => x !== s) : [...sources, s]);

  return (
    <form
      className={`panel p-5 sm:p-6 ${editing ? "border-accent/50 ring-4 ring-accent-soft" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          query_string: query,
          date_from: dateFrom || null,
          date_to: dateTo || null,
          sources,
          parent_version_id: editing?.id ?? null,
        });
      }}
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <label htmlFor="query" className="font-medium">
          {editing ? `Edit v${editing.version_number}` : "New search"}
        </label>
        {editing && (
          <span className="flex items-center gap-3 text-sm text-muted">
            Saving creates a new version; v{editing.version_number} stays as it is.
            <button type="button" className="btn-quiet" onClick={onCancel}>
              Cancel edit
            </button>
          </span>
        )}
      </div>
      <textarea
        id="query"
        className="input w-full resize-y font-mono text-[15px] leading-relaxed"
        rows={3}
        required
        value={query}
        placeholder='"type 2 diabetes" AND metformin NOT mice'
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
        }}
      />
      <p className="mt-2 text-xs text-faint">
        Combine terms with AND, OR and NOT, and quote exact phrases. PubMed field tags such as [tiab] also work.
      </p>

      <div className="mt-5 flex flex-wrap items-end gap-x-6 gap-y-4">
        <fieldset className="flex flex-col gap-1.5">
          <legend className="label mb-1.5">Sources</legend>
          <div className="flex gap-2">
            {(["pubmed", "europepmc"] as const).map((s) => (
              <label
                key={s}
                className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors has-focus-visible:outline-2 has-focus-visible:outline-accent ${
                  sources.includes(s) ? "border-accent/60 bg-accent-soft text-ink" : "border-rule bg-surface text-muted"
                }`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={sources.includes(s)}
                  onChange={() => toggle(s)}
                />
                <span
                  className={`flex size-3.5 items-center justify-center rounded-[4px] border ${
                    sources.includes(s) ? "border-accent bg-accent" : "border-faint"
                  }`}
                  aria-hidden
                >
                  {sources.includes(s) && (
                    <svg viewBox="0 0 12 12" className="size-2.5 fill-none stroke-accent-ink stroke-2">
                      <path d="M2.5 6.5 5 9l4.5-6" />
                    </svg>
                  )}
                </span>
                {SOURCE_NAMES[s]}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex flex-col gap-1.5">
          <span className="label">Published from</span>
          <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">to</span>
          <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        <button className="btn-primary ml-auto" disabled={disabled || sources.length === 0 || !query.trim()}>
          {busy && <Spinner />}
          {busy ? "Counting hits" : editing ? "Save as new version" : "Count hits"}
        </button>
      </div>
    </form>
  );
}

function ImportButton({ busy, onImport }: { busy: boolean; onImport: (name: string, text: string) => void }) {
  return (
    <label
      className={`btn cursor-pointer has-focus-visible:outline-2 has-focus-visible:outline-accent ${busy ? "pointer-events-none opacity-50" : ""}`}
      title="A PubMed EFetch XML file or a Europe PMC search JSON file"
    >
      <svg viewBox="0 0 16 16" className="size-4 fill-none stroke-current stroke-[1.5]" aria-hidden>
        <path d="M8 2.5v7M5 6.5l3 3 3-3M3 11.5v2h10v-2" />
      </svg>
      Import a file
      <input
        type="file"
        accept=".xml,.json,application/xml,application/json,text/xml"
        className="sr-only"
        disabled={busy}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onImport(file.name, await file.text());
        }}
      />
    </label>
  );
}

function VersionItem({
  v,
  last,
  parent,
  others,
  canRevert,
  busy,
  panel,
  onClose,
  onFetch,
  onToggle,
  onRevert,
  onHistory,
  onDiff,
  onEdit,
}: {
  v: QueryVersion;
  last: boolean;
  parent?: QueryVersion;
  others: QueryVersion[];
  canRevert: boolean;
  busy: string | null;
  panel: Panel | null;
  onClose: () => void;
  onFetch: () => void;
  onToggle: (on: boolean) => void;
  onRevert: () => void;
  onHistory: () => void;
  onDiff: () => void;
  onEdit: () => void;
}) {
  const fetched = v.status === "fetched";
  const imported = v.sources.includes("import");
  const doing = (k: string) => busy === `${k}-${v.id}`;
  const dates =
    v.date_from || v.date_to ? `${v.date_from ? fmtDate(v.date_from) : "Any date"} to ${v.date_to ? fmtDate(v.date_to) : "today"}` : null;

  return (
    <li className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-4">
      <div className="flex flex-col items-center">
        <span
          className={`mt-4 flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums ${
            v.active
              ? "bg-accent text-accent-ink"
              : fetched
                ? "border border-rule bg-surface text-ink"
                : "border border-dashed border-faint text-muted"
          }`}
          title={v.active ? "In the working set" : fetched ? "Fetched, not in the working set" : "Counted, not fetched"}
        >
          v{v.version_number}
        </span>
        {!last && <span className="w-px flex-1 bg-rule" />}
      </div>

      <div className="pb-5">
        <article className={`panel p-4 sm:p-5 ${v.active ? "" : "bg-surface/60"}`}>
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
            <div className="min-w-0 flex-1">
              <p className={`font-mono text-[14px] leading-relaxed break-words ${imported ? "text-muted" : ""}`}>
                {v.query_string}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                {/* versions counted before per-source hits were stored only have the total */}
                {Object.entries(Object.keys(v.source_hits).length ? v.source_hits : { [v.sources[0]]: v.hit_count }).map(([s, n]) => (
                  <span key={s}>
                    <span className="font-medium text-ink tabular-nums">{n.toLocaleString()}</span>{" "}
                    {imported ? "records in file" : `in ${SOURCE_NAMES[s] ?? s}`}
                  </span>
                ))}
                {dates && <span>{dates}</span>}
                {parent && <span>Edited from v{parent.version_number}</span>}
                <span>{fmtTime(v.created_at)}</span>
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              {fetched ? (
                <>
                  <span className="text-sm text-muted">{v.active ? "In working set" : "Not in working set"}</span>
                  {doing("toggle") ? (
                    <Spinner />
                  ) : (
                    <Switch
                      checked={v.active}
                      disabled={busy !== null}
                      label={`v${v.version_number} in the working set`}
                      onChange={onToggle}
                    />
                  )}
                </>
              ) : (
                <span className="rounded-full border border-dashed border-faint px-2.5 py-0.5 text-xs text-muted">
                  Not fetched yet
                </span>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-rule pt-3">
            {!imported && (
              <button
                className={fetched ? "btn-quiet" : "btn-primary mr-1 py-1.5"}
                disabled={busy !== null}
                title="Downloads only the records not stored yet, then deduplicates, screens and tags PICO"
                onClick={onFetch}
              >
                {doing("fetch") && <Spinner />}
                {doing("fetch") ? "Fetching and screening" : fetched ? "Fetch again" : "Fetch and screen"}
              </button>
            )}
            {fetched && (
              <Link className="btn-quiet" href={`/records?version=${v.id}`}>
                Records
              </Link>
            )}
            {!imported && (
              <button className="btn-quiet" disabled={busy !== null} onClick={onEdit}>
                Edit
              </button>
            )}
            {fetched && others.length > 0 && (
              <button className="btn-quiet" onClick={panel?.kind === "diff" ? onClose : onDiff}>
                Compare
              </button>
            )}
            {canRevert && (
              <button
                className="btn-quiet"
                disabled={busy !== null}
                title="Make this the only version of its edit history in the working set"
                onClick={onRevert}
              >
                {doing("revert") && <Spinner />}
                Revert to this
              </button>
            )}
            {fetched && (
              <button className="btn-quiet" disabled={busy !== null} onClick={panel?.kind === "history" ? onClose : onHistory}>
                Run log
              </button>
            )}
          </div>

          {panel && (
            <div className="rise mt-4 border-t border-rule pt-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold">
                  {panel.kind === "run"
                    ? panel.title
                    : panel.kind === "history"
                      ? "Run log"
                      : panel.kind === "revert"
                        ? `Reverted to v${v.version_number}`
                        : "Compare versions"}
                </h3>
                <button className="btn-quiet" onClick={onClose} aria-label="Close">
                  Close
                </button>
              </div>
              {panel.kind === "run" && <RunSteps logs={panel.logs} />}
              {panel.kind === "history" && <History logs={panel.logs} />}
              {panel.kind === "revert" && <RevertResult v={v} data={panel.data} />}
              {panel.kind === "diff" && (
                <Diff v={v} others={others} initial={parent?.status === "fetched" ? parent.id : others[0].id} />
              )}
            </div>
          )}
        </article>
      </div>
    </li>
  );
}

/** The run log split into runs: a new run starts whenever the step order goes back to the start. */
function History({ logs }: { logs: RunLog[] }) {
  if (logs.length === 0) return <p className="text-sm text-muted">This version has not been run.</p>;
  const order = ["fetch", "dedupe", "screen", "pico"];
  const runs: RunLog[][] = [];
  for (const l of [...logs].reverse()) {
    const prev = runs.at(-1)?.at(-1);
    if (!prev || order.indexOf(l.step) <= order.indexOf(prev.step)) runs.push([l]);
    else runs.at(-1)!.push(l);
  }
  runs.reverse();
  return (
    <div className="flex flex-col gap-5">
      {runs.slice(0, 6).map((r) => (
        <div key={r[0].id}>
          <p className="mb-2 text-xs text-muted">{fmtTime(r[0].started_at)}</p>
          {r === runs[0] ? (
            <RunSteps logs={r} />
          ) : (
            <ul className="flex flex-col gap-1 text-xs">
              {r.map((l) => (
                <li key={l.id} className={l.status === "error" ? "text-exc" : "text-muted"}>
                  <span className="font-medium text-ink">{l.step}</span>{" "}
                  {l.status === "error"
                    ? String(l.details.error)
                    : stepFacts(l.details)
                        .map(([k, val]) => `${k.toLowerCase()} ${val}`)
                        .join(", ")}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function RevertResult({ v, data }: { v: QueryVersion; data: Revert }) {
  const ok = data.identical_to_original;
  return (
    <div className="flex flex-col gap-4">
      <p
        className={`flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-sm ${ok ? "bg-inc-bg text-inc" : "bg-may-bg text-may"}`}
      >
        <svg viewBox="0 0 16 16" className="mt-0.5 size-4 shrink-0 fill-none stroke-current stroke-2" aria-hidden>
          {ok ? <path d="M3 8.5 6.5 12 13 4.5" /> : <path d="M8 4v5M8 11.5v.5" />}
        </svg>
        <span>
          v{v.version_number} is the working set again: {data.records.toLocaleString()} records in{" "}
          {data.groups.toLocaleString()} duplicate {data.groups === 1 ? "group" : "groups"}.{" "}
          {ok
            ? "Records and groups are identical to when it was first fetched."
            : "The groups differ from when it was first fetched, most likely because a reviewer changed a duplicate since."}
        </span>
      </p>
      <RunSteps logs={data.logs} />
    </div>
  );
}

function Diff({ v, others, initial }: { v: QueryVersion; others: QueryVersion[]; initial: number }) {
  const [against, setAgainst] = useState(initial);
  const [data, setData] = useState<VersionDiff | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .diff(v.id, against)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [v.id, against]);

  return (
    <div className="flex flex-col gap-5">
      <label className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">v{v.version_number} compared with</span>
        <select className="input py-1" value={against} onChange={(e) => setAgainst(Number(e.target.value))}>
          {others.map((o) => (
            <option key={o.id} value={o.id}>
              v{o.version_number}: {o.query_string.slice(0, 50)}
            </option>
          ))}
        </select>
      </label>
      <ErrorNote>{error}</ErrorNote>
      {data && (
        <>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-4">
            {(
              [
                ["Added", data.added.length, "text-inc"],
                ["Removed", data.removed.length, "text-exc"],
                ["Unchanged", data.unchanged, ""],
                ["Newly merged groups", data.merged.length, "text-accent"],
              ] as const
            ).map(([k, n, c]) => (
              <div key={k} className="bg-surface px-4 py-3">
                <dt className="text-xs text-muted">{k}</dt>
                <dd className={`font-serif text-2xl font-semibold tabular-nums ${c}`}>{n.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
          <DiffList title="Added" records={data.added} />
          <DiffList title="Removed" records={data.removed} />
          {data.merged.length > 0 && (
            <div>
              <h4 className="mb-1 text-sm font-semibold">Newly merged groups</h4>
              <p className="mb-3 text-xs text-muted">
                Records that this version groups as one study and the other does not. A group whose members were
                judged differently needs a reviewer.
              </p>
              <ul className="flex flex-col gap-2">
                {data.merged.map((g) => (
                  <li
                    key={g.records[0].id}
                    className={`rounded-lg border p-3 ${g.conflict ? "border-exc/40 bg-exc-bg/40" : "border-rule"}`}
                  >
                    {g.conflict && (
                      <p className="mb-2 text-xs font-medium text-exc">Members were screened differently</p>
                    )}
                    <ul className="flex flex-col gap-1.5">
                      {g.records.map((r) => (
                        <BriefRow key={r.id} r={r} />
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function DiffList({ title, records }: { title: string; records: RecordBrief[] }) {
  const [all, setAll] = useState(false);
  if (records.length === 0) return null;
  const shown = all ? records : records.slice(0, 8);
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold">{title}</h4>
      <ul className="flex flex-col gap-1.5">
        {shown.map((r) => (
          <BriefRow key={r.id} r={r} />
        ))}
      </ul>
      {records.length > shown.length && (
        <button className="btn-quiet mt-2" onClick={() => setAll(true)}>
          Show all {records.length}
        </button>
      )}
    </div>
  );
}

function BriefRow({ r }: { r: RecordBrief }) {
  return (
    <li className="flex items-start gap-3 text-sm">
      <StatusBadge status={r.status} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <Link className="font-serif leading-snug hover:text-accent" href={`/records/${r.id}`}>
          {r.title || "Untitled record"}
        </Link>
        <p className="text-xs text-muted">
          {[r.first_author, r.year].filter(Boolean).join(", ")}
          {r.reason && <span className="text-faint"> ({r.reason})</span>}
        </p>
      </div>
    </li>
  );
}
