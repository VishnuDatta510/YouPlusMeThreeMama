"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type QueryVersion, type RunLog, type VersionDiff } from "@/lib/api";

export default function QueriesPage() {
  const [versions, setVersions] = useState<QueryVersion[]>([]);
  const [logs, setLogs] = useState<{ version: number; title: string; items: RunLog[] } | null>(null);
  const [diff, setDiff] = useState<{ version: number; data: VersionDiff } | null>(null);
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

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
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          run("preview", () =>
            api.preview({ query_string: query, date_from: dateFrom || null, date_to: dateTo || null }),
          );
        }}
      >
        <h1 className="text-xl font-semibold">Search PubMed</h1>
        <label className="flex flex-col gap-1 text-sm">
          Keyphrases (supports AND / OR / NOT and &quot;quoted phrases&quot;)
          <textarea
            className="input font-mono"
            rows={2}
            required
            value={query}
            placeholder='"type 2 diabetes" AND metformin NOT mice'
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            Published from
            <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            to
            <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <button className="btn-primary" disabled={busy !== null}>
            {busy === "preview" ? "Counting…" : "Preview hit count"}
          </button>
        </div>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      </form>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Query versions</h2>
        {versions.length === 0 ? (
          <p className="text-sm text-neutral-500">No queries yet. Preview one above.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-neutral-300 dark:border-neutral-700">
              <tr>
                <th className="py-2 pr-3">v</th>
                <th className="pr-3">Query</th>
                <th className="pr-3">Dates</th>
                <th className="pr-3 text-right">Hits</th>
                <th className="pr-3">Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.id} className="border-b border-neutral-200 dark:border-neutral-800">
                  <td className="py-2 pr-3">{v.version_number}</td>
                  <td className="pr-3 font-mono">{v.query_string}</td>
                  <td className="whitespace-nowrap pr-3">
                    {v.date_from ?? "…"} – {v.date_to ?? "…"}
                  </td>
                  <td className="pr-3 text-right">{v.hit_count.toLocaleString()}</td>
                  <td className="pr-3">{v.status}</td>
                  <td className="flex justify-end gap-3 whitespace-nowrap py-2">
                    <button
                      className="btn"
                      disabled={busy !== null}
                      onClick={() =>
                        run(`fetch-${v.id}`, async () =>
                          setLogs({ version: v.version_number, title: "Last run", items: await api.runPipeline(v.id) }),
                        )
                      }
                    >
                      {busy === `fetch-${v.id}` ? "Running…" : v.status === "fetched" ? "Re-run" : "Fetch & screen"}
                    </button>
                    {v.status === "fetched" && (
                      <button
                        className="text-blue-600 hover:underline"
                        onClick={() =>
                          api
                            .runs(v.id)
                            .then((items) => setLogs({ version: v.version_number, title: "Run history", items }))
                            .catch((e) => setError(e.message))
                        }
                      >
                        Log
                      </button>
                    )}
                    {v.status === "fetched" && v.parent_version_id !== null && (
                      <button
                        className="text-blue-600 hover:underline"
                        title="Records gained and lost compared with the previous version"
                        onClick={() =>
                          api
                            .diff(v.id)
                            .then((data) => setDiff({ version: v.version_number, data }))
                            .catch((e) => setError(e.message))
                        }
                      >
                        Diff
                      </button>
                    )}
                    {v.status === "fetched" && (
                      <Link className="text-blue-600 hover:underline" href={`/records?version=${v.id}`}>
                        Records
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {diff && (
        <section className="text-sm">
          <h2 className="mb-2 text-lg font-semibold">
            v{diff.version} vs v{versions.find((v) => v.id === diff.data.against)?.version_number ?? "?"}
          </h2>
          <p className="mb-2 text-neutral-500">
            {diff.data.added.length} added, {diff.data.removed.length} removed, {diff.data.unchanged} unchanged
          </p>
          {(["added", "removed"] as const).map((kind) =>
            diff.data[kind].length ? (
              <div key={kind} className="mb-3">
                <h3 className={`font-medium ${kind === "added" ? "text-green-700" : "text-red-700"}`}>
                  {kind === "added" ? "+ Added" : "− Removed"}
                </h3>
                <ul className="ml-4 list-disc">
                  {diff.data[kind].map((r) => (
                    <li key={r.id}>
                      <Link className="hover:underline" href={`/records/${r.id}`}>
                        {r.title || "(untitled)"}
                      </Link>{" "}
                      <span className="text-xs text-neutral-500">
                        {r.year} PMID {r.pmid}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
        </section>
      )}

      {logs && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">
            {logs.title} (v{logs.version})
          </h2>
          <ul className="flex flex-col gap-1 text-sm">
            {logs.items.map((l, i) => (
              <li key={i} className={l.status === "error" ? "text-red-600" : ""}>
                <span className="text-xs text-neutral-500">{new Date(l.started_at).toLocaleString()}</span>{" "}
                <span className="font-medium">{l.step}</span> — {l.status}{" "}
                <code className="text-xs text-neutral-500">{JSON.stringify(l.details)}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
