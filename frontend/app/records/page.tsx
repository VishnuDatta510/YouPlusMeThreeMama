"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type QueryVersion, type RecordRow } from "@/lib/api";
import { StatusBadge } from "./badge";

export default function RecordsPage({ searchParams }: PageProps<"/records">) {
  const initialVersion = use(searchParams).version;
  const [version, setVersion] = useState(typeof initialVersion === "string" ? initialVersion : "");
  const [status, setStatus] = useState("");
  const [versions, setVersions] = useState<QueryVersion[]>([]);
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.versions().then(setVersions).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    api
      .records({ status, query_version_id: version })
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [status, version]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-semibold">Records</h1>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            Status
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="include">Include</option>
              <option value="exclude">Exclude</option>
              <option value="maybe">Maybe</option>
              <option value="unscreened">Unscreened</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Query version
            <select className="input" value={version} onChange={(e) => setVersion(e.target.value)}>
              <option value="">All versions</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number}: {v.query_string.slice(0, 40)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {rows === null ? (
        <p className="text-sm text-neutral-500">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-neutral-500">No records match. Fetch a query version first.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="border-b border-neutral-300 dark:border-neutral-700">
            <tr>
              <th className="py-2">Title</th>
              <th className="pr-3">Year</th>
              <th className="pr-3">Status</th>
              <th className="w-56">Reason</th>
              <th className="pr-3">Source</th>
              <th className="text-right">Dups</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-neutral-200 align-top dark:border-neutral-800">
                <td className="py-2 pr-3">
                  <Link className="hover:underline" href={`/records/${r.id}`}>
                    {r.title || <em>(untitled)</em>}
                  </Link>
                  {r.pmid && <div className="text-xs text-neutral-500">PMID {r.pmid}</div>}
                </td>
                <td>{r.year ?? "—"}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td className="pr-3 text-neutral-600 dark:text-neutral-400">{r.reason}</td>
                <td>{r.source}</td>
                <td className="text-right">{r.duplicates || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rows && <p className="text-xs text-neutral-500">{rows.length} records (duplicates hidden)</p>}
    </div>
  );
}
