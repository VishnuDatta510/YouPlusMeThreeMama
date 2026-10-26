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
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? res.statusText);
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json();
}

const post = <T>(path: string, body?: unknown) =>
  json<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export type Reviewer = { id: number; email: string; name: string };

export type QueryVersion = {
  id: number;
  version_number: number;
  parent_version_id: number | null;
  query_string: string;
  date_from: string | null;
  date_to: string | null;
  sources: string[];
  hit_count: number;
  status: "previewed" | "fetched";
  created_at: string;
};

export type RunLog = {
  step: string;
  status: "running" | "ok" | "error";
  started_at: string;
  finished_at: string | null;
  details: Record<string, unknown>;
};

export type QueryIn = { query_string: string; date_from?: string | null; date_to?: string | null };

export const api = {
  login: (email: string, password: string) =>
    post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => json<Reviewer>("/auth/me"),
  preview: (q: QueryIn) => post<QueryVersion>("/queries/preview", q),
  versions: () => json<QueryVersion[]>("/queries"),
  runPipeline: (versionId: number) => post<RunLog[]>(`/queries/${versionId}/fetch`),
  records: (filters: { status?: string; query_version_id?: string }) => {
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
  title: string;
  year: number | null;
  status: Label | "unscreened";
  reason: string;
  source: "machine" | "human" | "";
  duplicates: number;
};

export type Decision =
  | { decision_type: "screen"; value: { label: Label; reason: string }; note?: string }
  | { decision_type: "duplicate"; value: { duplicate_of: number | null }; note?: string }
  | { decision_type: "pico"; value: { spans: Omit<Span, "text">[] }; note?: string };

export type RecordDetail = {
  id: number;
  pmid: string | null;
  doi: string | null;
  title: string;
  abstract: string;
  authors: string[];
  year: number | null;
  journal: string;
  language: string;
  publication_types: string[];
  mesh_terms: string[];
  status: { label: Label; reason: string; source: "machine" | "human" } | null;
  pico: Span[];
  duplicate_of: number | null;
  match: { match_method: string; score: number; needs_review: boolean } | null;
  duplicates: { id: number; pmid: string | null; title: string; year: number | null }[];
  history: {
    id: number;
    decision_type: Decision["decision_type"];
    value: Record<string, unknown>;
    note: string;
    reviewer: string;
    created_at: string;
  }[];
};
