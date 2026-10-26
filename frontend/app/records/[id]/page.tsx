"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  api,
  SOURCE_NAMES,
  type Decision,
  type Label,
  type PicoType,
  type RecordDetail,
  type Span,
} from "@/lib/api";
import { ErrorNote, LIST_KEY, PICO, QUEUE_KEY, Spinner, StatusBadge } from "../../ui";

type SaveProps = { busy: boolean; onSave: (d: Decision, others?: number[]) => Promise<boolean> };

const noSubscribe = () => () => {};
const stored = (key: string) => () => {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
};
const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

const METHODS: Record<string, string> = { doi: "Same DOI", pmid: "Same PMID", fuzzy: "Similar title" };

export default function RecordPage({ params }: PageProps<"/records/[id]">) {
  const { id } = use(params);
  const router = useRouter();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const queueRaw = useSyncExternalStore(noSubscribe, stored(QUEUE_KEY), () => null);
  const listSearch = useSyncExternalStore(noSubscribe, stored(LIST_KEY), () => null) ?? "";
  const queue = useMemo<number[]>(() => {
    try {
      return JSON.parse(queueRaw ?? "[]");
    } catch {
      return [];
    }
  }, [queueRaw]);
  const at = queue.indexOf(Number(id));
  const prev = at > 0 ? queue[at - 1] : null;
  const next = at >= 0 && at < queue.length - 1 ? queue[at + 1] : null;

  useEffect(() => {
    api.record(id).then(setRecord).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.key === "j" || e.key === "ArrowRight") && next) router.push(`/records/${next}`);
      if ((e.key === "k" || e.key === "ArrowLeft") && prev) router.push(`/records/${prev}`);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, router]);

  /** Appends `d` to this record, or to each of `others` (e.g. every member of a duplicate group), then reloads. */
  async function decide(d: Decision, others?: number[]) {
    if (!record) return false;
    setBusy(true);
    setError("");
    try {
      if (!others) setRecord(await api.decide(record.id, d));
      else {
        for (const o of others) await api.decide(o, d);
        setRecord(await api.record(record.id));
      }
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (!record)
    return error ? <ErrorNote>{error}</ErrorNote> : <p className="text-sm text-muted">Loading record</p>;

  const facts = [record.journal, record.year, record.pages && `pp. ${record.pages}`].filter(Boolean).join(", ");

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link href={`/records${listSearch}`} className="btn-quiet -ml-2">
          <svg viewBox="0 0 16 16" className="size-4 fill-none stroke-current stroke-[1.5]" aria-hidden>
            <path d="M10 3.5 5.5 8l4.5 4.5" />
          </svg>
          Records
        </Link>
        {at >= 0 && (
          <div className="flex items-center gap-1 text-sm text-muted">
            <span className="mr-2 tabular-nums">
              {at + 1} of {queue.length}
            </span>
            <NavButton to={prev} label="Previous record" hint="K" d="M10 3.5 5.5 8l4.5 4.5" />
            <NavButton to={next} label="Next record" hint="J" d="M6 3.5 10.5 8 6 12.5" />
          </div>
        )}
      </div>

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <article className="min-w-0">
          <p className="text-sm text-muted">{facts}</p>
          <h1 className="mt-2 font-serif text-[1.85rem] leading-[1.2] font-semibold tracking-tight text-pretty">
            {record.title || "Untitled record"}
          </h1>
          {record.authors.length > 0 && (
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              {record.authors.slice(0, 8).join(", ")}
              {record.authors.length > 8 && `, and ${record.authors.length - 8} more`}
            </p>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            {record.pmid && (
              <a
                className="rounded-md border border-rule bg-surface px-2 py-1 font-medium hover:border-faint"
                href={`https://pubmed.ncbi.nlm.nih.gov/${record.pmid}/`}
                target="_blank"
              >
                PubMed {record.pmid}
              </a>
            )}
            {record.doi && (
              <a
                className="max-w-full truncate rounded-md border border-rule bg-surface px-2 py-1 font-medium hover:border-faint"
                href={`https://doi.org/${record.doi}`}
                target="_blank"
              >
                DOI {record.doi}
              </a>
            )}
            <span className="rounded-md bg-uns-bg px-2 py-1 text-muted">
              From {SOURCE_NAMES[record.origin] ?? record.origin}
            </span>
            {record.language && record.language !== "eng" && (
              <span className="rounded-md bg-uns-bg px-2 py-1 text-muted">Language: {record.language}</span>
            )}
            {record.publication_types.slice(0, 4).map((t) => (
              <span key={t} className="rounded-md bg-uns-bg px-2 py-1 text-muted">
                {t}
              </span>
            ))}
          </div>

          <ErrorNote>{error && <span className="mt-4 block">{error}</span>}</ErrorNote>

          <PicoEditor
            key={JSON.stringify(record.pico)}
            text={record.abstract}
            spans={record.pico}
            busy={busy}
            onSave={decide}
          />

          {record.mesh_terms.length > 0 && (
            <section className="mt-10">
              <h2 className="mb-3 text-sm font-semibold">MeSH terms</h2>
              <ul className="flex flex-wrap gap-1.5">
                {record.mesh_terms.map((t) => (
                  <li key={t} className="rounded-md border border-rule px-2 py-0.5 text-xs text-muted">
                    {t}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-20">
          <ScreenForm
            key={record.history[0]?.id ?? 0}
            record={record}
            busy={busy}
            onSave={decide}
            onDone={() => next && router.push(`/records/${next}`)}
          />
          <Group record={record} busy={busy} onSave={decide} />
          <History record={record} busy={busy} onSave={decide} />
        </aside>
      </div>
    </div>
  );
}

function NavButton({ to, label, hint, d }: { to: number | null; label: string; hint: string; d: string }) {
  const icon = (
    <svg viewBox="0 0 16 16" className="size-4 fill-none stroke-current stroke-[1.5]" aria-hidden>
      <path d={d} />
    </svg>
  );
  if (to === null)
    return (
      <span className="btn pointer-events-none px-2 opacity-40" aria-disabled>
        {icon}
      </span>
    );
  return (
    <Link href={`/records/${to}`} className="btn px-2" aria-label={label} title={`${label} (${hint})`}>
      {icon}
    </Link>
  );
}

/** Plain abstract text with the headings of a structured abstract ("METHODS:") set in bold; the text is unchanged. */
const headed = (t: string) =>
  t.split(/((?:^|\n)[A-Z][A-Z ,/&-]{2,}:)/).map((p, i) => (i % 2 ? <b key={i} className="font-semibold">{p}</b> : p));

function Abstract({ text, spans }: { text: string; spans: Span[] }) {
  const parts = [];
  let cursor = 0;
  for (const s of [...spans].sort((a, b) => a.start - b.start)) {
    if (s.start < cursor) continue; // overlapping span: keep the first one visible
    parts.push(headed(text.slice(cursor, s.start)));
    parts.push(
      <mark key={s.start} title={PICO[s.type].label} className={`rounded-[3px] px-0.5 text-inherit pico-${s.type}`}>
        {text.slice(s.start, s.end)}
      </mark>,
    );
    cursor = s.end;
  }
  parts.push(headed(text.slice(cursor)));
  return (
    <p id="abstract" className="font-serif text-[17px] leading-[1.75] whitespace-pre-line">
      {parts}
    </p>
  );
}

/** Character offsets of the current text selection inside the abstract, trimmed of surrounding whitespace. */
function selectionOffsets(): { start: number; end: number } | null {
  const root = document.getElementById("abstract");
  const sel = window.getSelection();
  if (!root || !sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  const before = document.createRange();
  before.setStart(root, 0);
  before.setEnd(range.startContainer, range.startOffset);
  const raw = range.toString();
  const start = before.toString().length + (raw.length - raw.trimStart().length);
  const end = start + raw.trim().length;
  return end > start ? { start, end } : null;
}

function PicoEditor({ text, spans, busy, onSave }: SaveProps & { text: string; spans: Span[] }) {
  const [draft, setDraft] = useState(spans);
  const [hint, setHint] = useState("");
  const dirty = JSON.stringify(draft) !== JSON.stringify(spans);

  function addSelection(type: PicoType) {
    const o = selectionOffsets();
    if (!o) return setHint("Select a phrase in the abstract first.");
    if (draft.some((s) => o.start < s.end && s.start < o.end)) return setHint("That overlaps a phrase already tagged.");
    setHint("");
    setDraft([...draft, { type, ...o, text: text.slice(o.start, o.end) }].sort((a, b) => a.start - b.start));
    window.getSelection()?.removeAllRanges();
  }

  if (!text)
    return (
      <section className="mt-10 rounded-xl border border-dashed border-rule px-6 py-10 text-center text-sm text-muted">
        This record has no abstract, so there is nothing to tag. Open it at the source to screen the full text.
      </section>
    );

  return (
    <>
      <section className="mt-10">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-3">
          <h2 className="text-sm font-semibold">Abstract</h2>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="mr-1 text-muted">Tag selection as</span>
            {(Object.keys(PICO) as PicoType[]).map((k) => (
              <button
                key={k}
                className={`rounded-md px-2 py-1 font-medium text-ink transition-transform active:scale-95 pico-${k}`}
                title={`Tag the selected phrase as ${PICO[k].label.toLowerCase()}`}
                // keep the text selection alive while clicking
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addSelection(k)}
              >
                {PICO[k].label}
              </button>
            ))}
          </div>
        </div>
        {hint && <p className="mb-3 text-sm text-exc">{hint}</p>}
        <Abstract text={text} spans={draft} />
      </section>

      <section className="mt-10">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">PICO</h2>
          {dirty && <span className="text-xs text-may">Unsaved changes</span>}
        </div>
        {draft.length === 0 ? (
          <p className="text-sm text-muted">
            Nothing tagged yet. Select a phrase in the abstract and choose what it describes.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {(Object.keys(PICO) as PicoType[]).map((k) => {
              const of = draft.map((s, i) => [s, i] as const).filter(([s]) => s.type === k);
              return (
                <div key={k} className="panel p-3.5">
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted">
                    <span className={`size-2 rounded-full pico-dot-${k}`} aria-hidden />
                    {PICO[k].label}
                  </h3>
                  {of.length === 0 ? (
                    <p className="text-xs text-faint">None tagged</p>
                  ) : (
                    <ul className="flex flex-col gap-1.5">
                      {of.map(([s, i]) => (
                        <li key={`${s.start}-${s.end}`} className="group flex items-start gap-2 text-sm">
                          <span className="flex-1 leading-snug">{s.text}</span>
                          <select
                            aria-label="Change what this phrase describes"
                            className="rounded border border-transparent bg-transparent text-xs text-muted hover:border-rule"
                            value={s.type}
                            onChange={(e) =>
                              setDraft(draft.map((d, j) => (j === i ? { ...d, type: e.target.value as PicoType } : d)))
                            }
                          >
                            {(Object.keys(PICO) as PicoType[]).map((t) => (
                              <option key={t} value={t}>
                                {PICO[t].label}
                              </option>
                            ))}
                          </select>
                          <button
                            className="text-xs text-faint hover:text-exc"
                            aria-label={`Remove "${s.text}"`}
                            onClick={() => setDraft(draft.filter((_, j) => j !== i))}
                          >
                            Remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {dirty && (
          <div className="mt-4 flex gap-2">
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() =>
                onSave({
                  decision_type: "pico",
                  value: { spans: draft.map(({ type, start, end }) => ({ type, start, end })) },
                })
              }
            >
              Save PICO
            </button>
            <button className="btn" onClick={() => setDraft(spans)}>
              Discard changes
            </button>
          </div>
        )}
      </section>
    </>
  );
}

const LABELS: { value: Label; text: string; key: string; on: string }[] = [
  { value: "include", text: "Include", key: "I", on: "border-inc bg-inc-bg text-inc" },
  { value: "maybe", text: "Maybe", key: "M", on: "border-may bg-may-bg text-may" },
  { value: "exclude", text: "Exclude", key: "E", on: "border-exc bg-exc-bg text-exc" },
];

const REASONS = [
  "Wrong population",
  "Wrong intervention",
  "Wrong comparator",
  "Wrong outcome",
  "Wrong study design",
  "Not primary research",
  "Full text not available",
];

function ScreenForm({ record, busy, onSave, onDone }: SaveProps & { record: RecordDetail; onDone: () => void }) {
  const [label, setLabel] = useState<Label>(record.status?.label ?? "include");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const reasonInput = useRef<HTMLInputElement>(null);
  const size = record.group.length;

  async function save(l: Label, advance: boolean) {
    if (await onSave({ decision_type: "screen", value: { label: l, reason }, note })) {
      setReason("");
      setNote("");
      if (advance) onDone();
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey || busy) return;
      const k = e.key.toLowerCase();
      if (k === "i" || k === "m") {
        e.preventDefault();
        setLabel(k === "i" ? "include" : "maybe");
        save(k === "i" ? "include" : "maybe", true);
      }
      if (k === "e") {
        e.preventDefault();
        setLabel("exclude");
        reasonInput.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <section className="panel p-5">
      <h2 className="mb-3 text-sm font-semibold">Screening decision</h2>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={record.status?.label ?? "unscreened"} />
        <span className="text-xs text-muted">
          {record.status?.source === "human"
            ? "Decided by a reviewer"
            : record.status
              ? "Suggested by the screening rules"
              : "Not screened yet"}
        </span>
      </div>
      {record.status?.reason && (
        <p className="mt-2 border-l-2 border-rule pl-3 text-sm leading-relaxed text-muted">{record.status.reason}</p>
      )}

      {record.conflict && (
        <div className="mt-4 rounded-lg bg-exc-bg p-3 text-sm text-exc">
          <p className="font-medium">Reviewers disagree</p>
          <p className="mt-0.5 text-xs">The newest decision applies until everyone agrees. Latest votes:</p>
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {/* every group member carries the same votes, so show each reviewer's vote once */}
            {[...new Set(record.group.flatMap((m) => m.votes.map((v) => `${v.reviewer}\t${v.label}`)))].map((v) => {
              const [who, l] = v.split("\t");
              return (
                <li key={v} className="flex justify-between gap-2 text-ink">
                  <span>{who}</span>
                  <span className="font-medium capitalize">{l}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <form
        className="mt-5 flex flex-col gap-3 border-t border-rule pt-4"
        onSubmit={(e) => {
          e.preventDefault();
          // Enter in the reason field (the E shortcut's path) moves on; the button stays on this record.
          save(label, document.activeElement === reasonInput.current);
        }}
      >
        <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Decision">
          {LABELS.map((l) => (
            <button
              type="button"
              role="radio"
              aria-checked={label === l.value}
              key={l.value}
              className={`flex flex-col items-center gap-0.5 rounded-lg border py-2 text-sm font-medium transition-colors ${
                label === l.value ? l.on : "border-rule text-muted hover:border-faint hover:text-ink"
              }`}
              onClick={() => setLabel(l.value)}
            >
              {l.text}
              <span className="text-[10px] font-normal opacity-70">{l.key}</span>
            </button>
          ))}
        </div>
        <input
          ref={reasonInput}
          className="input"
          list="reasons"
          placeholder={label === "exclude" ? "Reason, required to exclude" : "Reason (optional)"}
          aria-label="Reason"
          required={label === "exclude"}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <datalist id="reasons">
          {REASONS.map((r) => (
            <option key={r} value={r} />
          ))}
        </datalist>
        <textarea
          className="input resize-y"
          rows={2}
          placeholder="Note for other reviewers (optional)"
          aria-label="Note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button className="btn-primary" disabled={busy}>
          {busy && <Spinner />}
          Save decision
        </button>
        <p className="text-xs leading-relaxed text-faint">
          {size > 1 && `Applies to all ${size} records in this duplicate group. `}
          Press <span className="kbd">I</span> or <span className="kbd">M</span> to decide and move on,{" "}
          <span className="kbd">E</span> to write an exclusion reason, <span className="kbd">J</span>{" "}
          <span className="kbd">K</span> to move between records.
        </p>
      </form>
    </section>
  );
}

function Group({ record, busy, onSave }: SaveProps & { record: RecordDetail }) {
  const [target, setTarget] = useState("");
  const mark = (duplicate_of: number | null, note = "") =>
    onSave({ decision_type: "duplicate", value: { duplicate_of }, note });
  const others = record.group.filter((m) => m.id !== record.id);

  return (
    <section className="panel p-5">
      <h2 className="mb-3 text-sm font-semibold">Duplicates</h2>

      {record.duplicate_of !== null && (
        <div className="mb-4 flex flex-col gap-2 text-sm">
          <p>
            This is a copy of{" "}
            <Link className="link font-medium" href={`/records/${record.duplicate_of}`}>
              record #{record.duplicate_of}
            </Link>
            , which is the one screened and exported.
            {record.match && (
              <span className="text-muted">
                {" "}
                {METHODS[record.match.match_method] ?? record.match.match_method}
                {record.match.match_method === "fuzzy" && `, score ${Math.round(record.match.score)}`}.
              </span>
            )}
          </p>
          {record.match?.needs_review && (
            <p className="rounded-lg bg-may-bg px-3 py-2 text-xs text-may">
              The titles are similar but not identical. Confirm it is the same report, or separate it.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {record.match?.needs_review && (
              <button className="btn py-1.5" disabled={busy} onClick={() => mark(record.duplicate_of)}>
                Confirm duplicate
              </button>
            )}
            <button className="btn py-1.5" disabled={busy} onClick={() => mark(null)}>
              Not a duplicate
            </button>
          </div>
        </div>
      )}

      {others.length > 0 ? (
        <ul className="flex flex-col divide-y divide-rule rounded-lg border border-rule">
          {record.group.map((m) => (
            <li key={m.id} className={`p-3 text-sm ${m.id === record.id ? "bg-paper" : ""}`}>
              <div className="flex items-start justify-between gap-2">
                {m.id === record.id ? (
                  <span className="font-medium">This record</span>
                ) : (
                  <Link className="link font-medium" href={`/records/${m.id}`}>
                    #{m.id}
                  </Link>
                )}
                <span className="text-xs text-muted">
                  {SOURCE_NAMES[m.origin] ?? m.origin}
                  {m.year ? `, ${m.year}` : ""}
                </span>
              </div>
              {m.id !== record.id && <p className="mt-1 line-clamp-2 font-serif text-[13px] leading-snug">{m.title}</p>}
            </li>
          ))}
        </ul>
      ) : (
        record.duplicate_of === null && <p className="text-sm text-muted">No other record matches this one.</p>
      )}

      {record.duplicate_of === null && others.length > 0 && (
        <button
          className="btn mt-3 w-full py-1.5"
          disabled={busy}
          onClick={() =>
            onSave(
              { decision_type: "duplicate", value: { duplicate_of: null }, note: `Group split from #${record.id}` },
              others.map((d) => d.id),
            )
          }
        >
          {others.length === 1 ? "These are different reports" : "None of these are copies"}
        </button>
      )}

      {record.duplicate_of === null && (
        <form
          className="mt-4 flex gap-2 border-t border-rule pt-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await mark(Number(target))) setTarget("");
          }}
        >
          <input
            className="input w-0 flex-1"
            type="number"
            min={1}
            required
            placeholder="Record number"
            aria-label="Mark as a copy of record number"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
          <button className="btn" disabled={busy}>
            Mark as copy
          </button>
        </form>
      )}

      {record.versions.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-rule pt-4 text-xs">
          <span className="mr-1 text-muted">Found by</span>
          {record.versions.map((v) => (
            <Link
              key={v.id}
              href={`/records?version=${v.id}`}
              className={`rounded-full px-2 py-0.5 font-medium tabular-nums ${
                v.active ? "bg-accent text-accent-ink" : "border border-rule text-muted"
              }`}
              title={v.active ? "In the working set" : "Not in the working set"}
            >
              v{v.version_number}
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

function describe(h: RecordDetail["history"][number]) {
  const v = h.value;
  if (h.decision_type === "screen") return `${String(v.label).replace(/^\w/, (c) => c.toUpperCase())}${v.reason ? `: ${v.reason}` : ""}`;
  if (h.decision_type === "duplicate") return v.duplicate_of ? `Marked as a copy of #${v.duplicate_of}` : "Marked as not a duplicate";
  return `Edited PICO (${(v.spans as Span[]).length} phrases)`;
}

function History({ record, busy, onSave }: SaveProps & { record: RecordDetail }) {
  // History is newest first, so the first entry of each type is the one in effect; older ones can be restored.
  const current = new Set(
    record.history.map((h) => record.history.find((x) => x.decision_type === h.decision_type)!.id),
  );
  return (
    <section className="panel p-5">
      <h2 className="mb-3 text-sm font-semibold">History</h2>
      {record.history.length === 0 ? (
        <p className="text-sm text-muted">No reviewer has changed this record. Every change is kept here.</p>
      ) : (
        <ol className="flex flex-col">
          {record.history.map((h, i) => (
            <li key={h.id} className="relative grid grid-cols-[0.75rem_minmax(0,1fr)] gap-x-3 pb-4 last:pb-0">
              <span
                className={`mt-1.5 size-2 rounded-full ${current.has(h.id) ? "bg-accent" : "bg-rule"}`}
                aria-hidden
              />
              {i < record.history.length - 1 && (
                <span className="absolute top-4 bottom-0 left-[3.5px] w-px bg-rule" aria-hidden />
              )}
              <div className="text-sm">
                <p className={current.has(h.id) ? "" : "text-muted"}>{describe(h)}</p>
                {h.note && <p className="mt-0.5 text-xs text-muted italic">{h.note}</p>}
                <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-faint">
                  <span>
                    {h.reviewer}, {new Date(h.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                  </span>
                  {!current.has(h.id) && (
                    <button
                      className="font-medium text-accent hover:underline disabled:opacity-50"
                      disabled={busy}
                      title="Adds this decision again as the newest one; nothing is deleted"
                      onClick={() =>
                        onSave({ decision_type: h.decision_type, value: h.value, note: `Restored decision #${h.id}` } as Decision)
                      }
                    >
                      Restore
                    </button>
                  )}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
