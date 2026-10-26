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

export const api = {
  login: (email: string, password: string) =>
    post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => json<Reviewer>("/auth/me"),
};
