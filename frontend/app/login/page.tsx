"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";
import { ErrorNote, Logo, Spinner } from "../ui";

const STEPS = [
  ["Search", "PubMed and Europe PMC, with every query edit kept as a version"],
  ["Deduplicate", "by DOI and PMID, then by fuzzy title within year and first author"],
  ["Screen", "with rules you can switch off, each exclusion giving its reason"],
  ["Tag PICO", "population, intervention, comparator and outcome in each abstract"],
  ["Review", "override any machine call, then export the included records"],
];

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
    <div className="mx-auto grid max-w-5xl items-center gap-12 py-4 md:grid-cols-[1.1fr_1fr] md:py-12">
      <section>
        <div className="mb-8 flex items-center gap-3">
          <Logo className="size-9" />
          <span className="font-serif text-2xl font-semibold">Mini-Rayyan</span>
        </div>
        <h1 className="max-w-md font-serif text-4xl leading-[1.15] font-semibold tracking-tight">
          From a search string to the studies that answer it.
        </h1>
        <ol className="mt-8 flex flex-col gap-4">
          {STEPS.map(([name, text], i) => (
            <li key={name} className="flex gap-4">
              <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-rule bg-surface text-xs font-semibold text-muted tabular-nums">
                {i + 1}
              </span>
              <p className="text-[15px] leading-relaxed text-muted">
                <span className="font-medium text-ink">{name}</span> {text}
              </p>
            </li>
          ))}
        </ol>
      </section>

      <form onSubmit={submit} className="panel flex flex-col gap-5 p-7 shadow-[0_1px_2px_rgb(0_0_0/0.04)] sm:p-8">
        <div>
          <h2 className="font-serif text-xl font-semibold">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your reviewer account.</p>
        </div>
        <label className="flex flex-col gap-1.5">
          <span className="label">Email</span>
          <input
            className="input"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Password</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            required
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <ErrorNote>{error}</ErrorNote>
        <button className="btn-primary py-2.5" disabled={busy}>
          {busy && <Spinner />}
          {busy ? "Signing in" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
