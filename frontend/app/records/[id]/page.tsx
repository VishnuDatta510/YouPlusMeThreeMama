"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type Decision, type Label, type PicoType, type RecordDetail, type Span } from "@/lib/api";
import { PICO, StatusBadge } from "../badge";

export default function RecordPage({ params }: PageProps<"/records/[id]">) {
  const { id } = use(params);
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.record(id).then(setRecord).catch((e) => setError(e.message));
  }, [id]);

  async function decide(d: Decision) {
    if (!record) return false;
    setBusy(true);
    setError("");
    try {
      setRecord(await api.decide(record.id, d));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (!record) return <p className="text-sm text-neutral-500">{error || "Loading…"}</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link className="text-sm text-blue-600 hover:underline" href="/records">
          ← Records
        </Link>
        <h1 className="mt-2 text-xl font-semibold">{record.title || "(untitled)"}</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          {record.authors.slice(0, 6).join(", ")}
          {record.authors.length > 6 && ", et al."} · {record.journal} · {record.year ?? "n.d."}
          {record.language && record.language !== "eng" && ` · ${record.language}`}
        </p>
        <p className="mt-1 flex gap-4 text-sm">
          {record.pmid && (
            <a className="text-blue-600 hover:underline" href={`https://pubmed.ncbi.nlm.nih.gov/${record.pmid}/`} target="_blank">
              PMID {record.pmid}
            </a>
          )}
          {record.doi && (
            <a className="text-blue-600 hover:underline" href={`https://doi.org/${record.doi}`} target="_blank">
              doi:{record.doi}
            </a>
          )}
        </p>
      </div>

      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="flex flex-col gap-6">
          <section>
            <h2 className="mb-2 font-semibold">Abstract</h2>
            <Legend />
            <Abstract text={record.abstract} spans={record.pico} />
          </section>
          <PicoEditor key={JSON.stringify(record.pico)} spans={record.pico} busy={busy} onSave={decide} />
        </div>

        <aside className="flex flex-col gap-6">
          <ScreenForm record={record} busy={busy} onSave={decide} />
          <Duplicates record={record} busy={busy} onSave={decide} />
          <History record={record} />
        </aside>
      </div>
    </div>
  );
}

type SaveProps = { busy: boolean; onSave: (d: Decision) => Promise<boolean> };

function Legend() {
  return (
    <div className="mb-2 flex flex-wrap gap-2 text-xs">
      {Object.entries(PICO).map(([k, v]) => (
        <span key={k} className={`rounded px-1.5 py-0.5 ${v.className}`}>
          {k} · {v.label}
        </span>
      ))}
    </div>
  );
}

function Abstract({ text, spans }: { text: string; spans: Span[] }) {
  if (!text) return <p className="text-sm text-neutral-500">No abstract available.</p>;
  const parts = [];
  let cursor = 0;
  for (const s of [...spans].sort((a, b) => a.start - b.start)) {
    if (s.start < cursor) continue; // overlapping span: keep the first one visible
    parts.push(text.slice(cursor, s.start));
    parts.push(
      <mark key={s.start} title={PICO[s.type].label} className={`rounded px-0.5 text-inherit ${PICO[s.type].className}`}>
        {text.slice(s.start, s.end)}
      </mark>,
    );
    cursor = s.end;
  }
  parts.push(text.slice(cursor));
  return <p className="whitespace-pre-line leading-relaxed">{parts}</p>;
}

function PicoEditor({ spans, busy, onSave }: SaveProps & { spans: Span[] }) {
  const [draft, setDraft] = useState(spans);
  const dirty = JSON.stringify(draft) !== JSON.stringify(spans);
  return (
    <section>
      <h2 className="mb-2 font-semibold">PICO spans</h2>
      {draft.length === 0 ? (
        <p className="text-sm text-neutral-500">No spans tagged.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {draft.map((s, i) => (
            <li key={`${s.start}-${s.end}`} className="flex items-start gap-2">
              <select
                aria-label="Span type"
                className="input py-0.5"
                value={s.type}
                onChange={(e) =>
                  setDraft(draft.map((d, j) => (j === i ? { ...d, type: e.target.value as PicoType } : d)))
                }
              >
                {Object.keys(PICO).map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
              <span className={`flex-1 rounded px-1 ${PICO[s.type].className}`}>{s.text}</span>
              <button className="btn py-0.5" onClick={() => setDraft(draft.filter((_, j) => j !== i))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {dirty && (
        <div className="mt-3 flex gap-2">
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
            Save PICO changes
          </button>
          <button className="btn" onClick={() => setDraft(spans)}>
            Discard
          </button>
        </div>
      )}
    </section>
  );
}

function ScreenForm({ record, busy, onSave }: SaveProps & { record: RecordDetail }) {
  const [label, setLabel] = useState<Label>(record.status?.label ?? "include");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  return (
    <section className="flex flex-col gap-2 text-sm">
      <h2 className="font-semibold">Screening</h2>
      <div className="flex items-center gap-2">
        <StatusBadge status={record.status?.label ?? "unscreened"} />
        {record.status && <span className="text-xs text-neutral-500">by {record.status.source}</span>}
      </div>
      {record.status?.reason && <p className="text-neutral-600 dark:text-neutral-400">{record.status.reason}</p>}
      <form
        className="flex flex-col gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await onSave({ decision_type: "screen", value: { label, reason }, note })) {
            setReason("");
            setNote("");
          }
        }}
      >
        <div className="flex gap-1" role="radiogroup" aria-label="Decision">
          {(["include", "exclude", "maybe"] as const).map((l) => (
            <button
              type="button"
              role="radio"
              aria-checked={label === l}
              key={l}
              className={`btn flex-1 capitalize ${label === l ? "border-blue-600 ring-1 ring-blue-600" : ""}`}
              onClick={() => setLabel(l)}
            >
              {l}
            </button>
          ))}
        </div>
        <input
          className="input"
          placeholder={label === "exclude" ? "Reason (required)" : "Reason (optional)"}
          required={label === "exclude"}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <textarea
          className="input"
          rows={2}
          placeholder="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button className="btn-primary" disabled={busy}>
          Save decision
        </button>
      </form>
    </section>
  );
}

function Duplicates({ record, busy, onSave }: SaveProps & { record: RecordDetail }) {
  const [target, setTarget] = useState("");
  const mark = (duplicate_of: number | null) => onSave({ decision_type: "duplicate", value: { duplicate_of } });
  return (
    <section className="flex flex-col gap-2 text-sm">
      <h2 className="font-semibold">Duplicates</h2>
      {record.duplicate_of !== null ? (
        <>
          <p>
            Duplicate of{" "}
            <Link className="text-blue-600 hover:underline" href={`/records/${record.duplicate_of}`}>
              #{record.duplicate_of}
            </Link>
            {record.match && (
              <span className="text-neutral-500">
                {" "}
                ({record.match.match_method}, score {Math.round(record.match.score)})
              </span>
            )}
          </p>
          {record.match?.needs_review && (
            <p className="text-amber-700 dark:text-amber-400">Fuzzy match: please confirm or unmark.</p>
          )}
          <button className="btn" disabled={busy} onClick={() => mark(null)}>
            Not a duplicate
          </button>
        </>
      ) : (
        <form
          className="flex gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await mark(Number(target))) setTarget("");
          }}
        >
          <input
            className="input w-24"
            type="number"
            min={1}
            required
            placeholder="Record #"
            aria-label="Duplicate of record id"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
          <button className="btn" disabled={busy}>
            Mark duplicate
          </button>
        </form>
      )}
      {record.duplicates.length > 0 && (
        <ul className="flex flex-col gap-1">
          {record.duplicates.map((d) => (
            <li key={d.id}>
              <Link className="text-blue-600 hover:underline" href={`/records/${d.id}`}>
                #{d.id}
              </Link>{" "}
              {d.title} {d.year && `(${d.year})`}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function describe(h: RecordDetail["history"][number]) {
  const v = h.value;
  if (h.decision_type === "screen") return `${v.label}${v.reason ? `: ${v.reason}` : ""}`;
  if (h.decision_type === "duplicate") return v.duplicate_of ? `duplicate of #${v.duplicate_of}` : "not a duplicate";
  return `PICO edited (${(v.spans as Span[]).length} spans)`;
}

function History({ record }: { record: RecordDetail }) {
  return (
    <section className="flex flex-col gap-2 text-sm">
      <h2 className="font-semibold">History</h2>
      {record.history.length === 0 ? (
        <p className="text-neutral-500">No human decisions yet.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {record.history.map((h) => (
            <li key={h.id} className="border-l-2 border-neutral-300 pl-2 dark:border-neutral-700">
              <div>{describe(h)}</div>
              {h.note && <div className="italic text-neutral-600 dark:text-neutral-400">“{h.note}”</div>}
              <div className="text-xs text-neutral-500">
                {h.reviewer} · {new Date(h.created_at).toLocaleString()}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
