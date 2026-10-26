const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "mr_token";

export const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY));
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (res.status === 401 && path !== "/auth/login") {
    setToken(null);
    // Full reload on purpose: drops all in-memory page state of the signed-out user.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ")
      : typeof body.detail === "string"
        ? body.detail
        : res.statusText;
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json();
}

const send = <T>(method: string, path: string, body?: unknown) =>
  json<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
const post = <T>(path: string, body?: unknown) => send<T>("POST", path, body);

export type Reviewer = { id: number; email: string; name: string };
export type Source = "pubmed" | "europepmc";
export const SOURCE_NAMES: Record<string, string> = { pubmed: "PubMed", europepmc: "Europe PMC", import: "File import" };

export type QueryVersion = {
  id: number;
  version_number: number;
  parent_version_id: number | null;
  query_string: string;
  date_from: string | null;
  date_to: string | null;
  sources: string[];
  hit_count: number;
  source_hits: Record<string, number>;
  status: "previewed" | "fetched";
  active: boolean;
  created_at: string;
};

export type RunLog = {
  id: number;
  query_version_id: number;
  step: string;
  status: "running" | "ok" | "error";
  started_at: string;
  finished_at: string | null;
  details: Record<string, unknown>;
};

export type Status = Label | "unscreened";
export type RecordBrief = {
  id: number;
  pmid: string | null;
  title: string;
  year: number | null;
  first_author: string;
  status: Status;
  reason: string;
};
export type VersionDiff = {
  against: number;
  added: RecordBrief[];
  removed: RecordBrief[];
  unchanged: number;
  merged: { records: RecordBrief[]; conflict: boolean }[];
};
export type Revert = { logs: RunLog[]; records: number; groups: number; identical_to_original: boolean };
export type Criterion = { key: string; label: string; why: string; basis: string; active: boolean };

export type QueryIn = {
  query_string: string;
  date_from?: string | null;
  date_to?: string | null;
  sources: Source[];
  parent_version_id?: number | null;
};

export type RecordFilters = { status?: string; query_version_id?: string; needs_review?: string; conflict?: string };

export const api = {
  login: (email: string, password: string) =>
    post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => json<Reviewer>("/auth/me"),
  preview: (q: QueryIn) => post<QueryVersion>("/queries/preview", q),
  versions: () => json<QueryVersion[]>("/queries"),
  runPipeline: (versionId: number) => post<RunLog[]>(`/queries/${versionId}/fetch`),
  setActive: (versionId: number, active: boolean) => send<RunLog[]>("PATCH", `/queries/${versionId}`, { active }),
  revert: (versionId: number) => post<Revert>(`/queries/${versionId}/revert`),
  runs: (versionId: number) => json<RunLog[]>(`/queries/${versionId}/runs`),
  diff: (versionId: number, against?: number) =>
    json<VersionDiff>(`/queries/${versionId}/diff${against ? `?against=${against}` : ""}`),
  importSnapshot: (filename: string, content: string) => post<RunLog[]>("/queries/import", { filename, content }),
  criteria: () => json<Criterion[]>("/screening/criteria"),
  setCriteria: (active: string[], note: string) => send<RunLog[]>("PUT", "/screening/criteria", { active, note }),
  records: (filters: RecordFilters) => {
    const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v) as [string, string][]);
    return json<RecordRow[]>(`/records?${qs}`);
  },
  record: (id: number | string) => json<RecordDetail>(`/records/${id}`),
  decide: (id: number, d: Decision) => post<RecordDetail>(`/records/${id}/decisions`, d),
  // Fetched as a blob (not a plain link) because the endpoint needs the bearer token.
  downloadIncludedCsv: async (queryVersionId?: string) => {
    const qs = queryVersionId ? `?query_version_id=${queryVersionId}` : "";
    const url = URL.createObjectURL(await (await request(`/export/included.csv${qs}`)).blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "included.csv" });
    a.click();
    URL.revokeObjectURL(url);
  },
};

export type Label = "include" | "exclude" | "maybe";
export type PicoType = "P" | "I" | "C" | "O";
export type Span = { type: PicoType; start: number; end: number; text: string };

export type RecordRow = {
  id: number;
  pmid: string | null;
  doi: string | null;
  title: string;
  first_author: string;
  journal: string;
  year: number | null;
  origin: string;
  status: Status;
  reason: string;
  source: "machine" | "human" | "";
  duplicates: number;
  needs_review: boolean;
  conflict: boolean;
};

export type Decision =
  | { decision_type: "screen"; value: { label: Label; reason: string }; note?: string }
  | { decision_type: "duplicate"; value: { duplicate_of: number | null }; note?: string }
  | { decision_type: "pico"; value: { spans: Omit<Span, "text">[] }; note?: string };

type ScreenState = { label: Label; reason: string; source: "machine" | "human" };

export type GroupMember = {
  id: number;
  pmid: string | null;
  title: string;
  year: number | null;
  journal: string;
  origin: string;
  status: ScreenState | null;
  votes: { reviewer: string; label: Label }[];
};

export type RecordDetail = {
  id: number;
  pmid: string | null;
  doi: string | null;
  title: string;
  abstract: string;
  authors: string[];
  year: number | null;
  journal: string;
  pages: string;
  language: string;
  publication_types: string[];
  mesh_terms: string[];
  origin: string;
  source_id: string | null;
  status: ScreenState | null;
  conflict: boolean;
  pico: Span[];
  duplicate_of: number | null;
  match: { match_method: string; score: number; needs_review: boolean } | null;
  duplicates: GroupMember[];
  group: GroupMember[];
  versions: { id: number; version_number: number; active: boolean }[];
  history: {
    id: number;
    decision_type: Decision["decision_type"];
    value: Record<string, unknown>;
    note: string;
    reviewer: string;
    created_at: string;
  }[];
};
