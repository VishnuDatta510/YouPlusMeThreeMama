"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("demo@minirayyan.dev");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      router.push("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto mt-16 flex w-full max-w-sm flex-col gap-3">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <label className="flex flex-col gap-1 text-sm">
        Email
        <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Password
        <input
          className="input"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <button className="btn-primary" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
