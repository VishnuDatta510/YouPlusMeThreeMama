"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Criterion, type RunLog } from "@/lib/api";
import { ErrorNote, PageHeader, RunSteps, Spinner, Switch } from "../ui";

export default function CriteriaPage() {
  const [criteria, setCriteria] = useState<Criterion[] | null>(null);
  const [active, setActive] = useState<Set<string>>(new Set());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RunLog[] | null>(null);

  function load(c: Criterion[]) {
    setCriteria(c);
    setActive(new Set(c.filter((x) => x.active).map((x) => x.key)));
  }
  const [numbers, setNumbers] = useState<Record<number, number>>({});
  useEffect(() => {
    api.criteria().then(load).catch((e) => setError(e.message));
    api
      .versions()
      .then((vs) => setNumbers(Object.fromEntries(vs.map((v) => [v.id, v.version_number]))))
      .catch(() => {});
  }, []);

  const dirty = !!criteria && criteria.some((c) => c.active !== active.has(c.key));

  async function save() {
    setBusy(true);
    setError("");
    try {
      setResult(await api.setCriteria([...active], note));
      setNote("");
      load(await api.criteria());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader title="Screening criteria">
        A record that fails an active criterion is excluded with that criterion as its reason. Switching one off
        reruns screening on the working set; earlier results are kept, and reviewer decisions always win.
      </PageHeader>

      <ErrorNote>{error}</ErrorNote>

      {criteria === null ? (
        !error && <p className="text-sm text-muted">Loading criteria</p>
      ) : (
        <>
          <ul className="panel divide-y divide-rule">
            {criteria.map((c) => {
              const on = active.has(c.key);
              return (
                <li key={c.key} className="flex items-start gap-4 px-5 py-4">
                  <div className="pt-0.5">
                    <Switch
                      checked={on}
                      label={c.label}
                      disabled={busy}
                      onChange={(v) => {
                        const next = new Set(active);
                        if (v) next.add(c.key);
                        else next.delete(c.key);
                        setActive(next);
                      }}
                    />
                  </div>
                  <div className={`min-w-0 flex-1 transition-opacity ${on ? "" : "opacity-60"}`}>
                    <p className="font-medium">
                      {c.label}
                      {c.active !== on && <span className="ml-2 text-xs font-normal text-may">Changed</span>}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-muted">{c.why}</p>
                    <p className="mt-1.5 text-xs text-faint">
                      {/* lower-case the first word unless it is an acronym such as MeSH */}
                      Checked using {/^[A-Z][a-z]+\b/.test(c.basis) ? c.basis[0].toLowerCase() + c.basis.slice(1) : c.basis}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <input
              className="input min-w-60 flex-1"
              placeholder="Why the criteria changed (kept in the log)"
              aria-label="Note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button className="btn-primary" disabled={!dirty || busy} onClick={save}>
              {busy && <Spinner />}
              {busy ? "Rescreening" : "Save and rescreen"}
            </button>
            {dirty && !busy && (
              <button className="btn" onClick={() => load(criteria)}>
                Discard
              </button>
            )}
          </div>
          <p className="mt-2 text-xs text-faint">
            {active.size} of {criteria.length} criteria active.
          </p>

          {result && (
            <section className="rise mt-8">
              <h2 className="mb-3 text-sm font-semibold">Rescreened the working set</h2>
              {/* one screen + PICO pass per version in the working set */}
              {[...new Set(result.map((l) => l.query_version_id))].map((id) => (
                <div key={id} className="mb-4">
                  <p className="mb-2 text-xs text-muted">v{numbers[id] ?? id}</p>
                  <RunSteps logs={result.filter((l) => l.query_version_id === id)} />
                </div>
              ))}
              <Link className="link mt-3 inline-block text-sm" href="/records">
                See the records
              </Link>
            </section>
          )}
        </>
      )}
    </div>
  );
}
