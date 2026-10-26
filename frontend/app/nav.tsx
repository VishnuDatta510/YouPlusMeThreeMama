"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";
import { Logo } from "./ui";

const LINKS = [
  { href: "/", label: "Searches", match: (p: string) => p === "/" },
  { href: "/records", label: "Records", match: (p: string) => p.startsWith("/records") },
  { href: "/criteria", label: "Criteria", match: (p: string) => p.startsWith("/criteria") },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [name, setName] = useState("");
  const hidden = path === "/login";

  useEffect(() => {
    if (!hidden) api.me().then((r) => setName(r.name)).catch(() => {});
  }, [hidden]);

  if (hidden) return null;
  return (
    <header className="sticky top-0 z-20 border-b border-rule bg-surface/90 backdrop-blur">
      <nav className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-4 sm:gap-6 sm:px-6">
        <Link href="/" className="mr-2 flex items-center gap-2 font-serif text-[17px] font-semibold sm:mr-4">
          <Logo />
          <span className="hidden sm:inline">Mini-Rayyan</span>
        </Link>
        {LINKS.map((l) => {
          const on = l.match(path);
          return (
            <Link
              key={l.href}
              href={l.href}
              aria-current={on ? "page" : undefined}
              className={`relative flex h-14 items-center px-2 text-sm font-medium transition-colors ${
                on ? "text-ink" : "text-muted hover:text-ink"
              }`}
            >
              {l.label}
              {on && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent" />}
            </Link>
          );
        })}
        <div className="ml-auto flex items-center gap-3 text-sm">
          {name && <span className="hidden text-muted md:inline">{name}</span>}
          <button
            className="btn-quiet"
            onClick={() => {
              setToken(null);
              router.push("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </nav>
    </header>
  );
}
