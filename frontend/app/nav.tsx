"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { setToken } from "@/lib/api";

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  if (path === "/login") return null;
  return (
    <header className="border-b border-neutral-200 dark:border-neutral-800">
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 text-sm">
        <Link href="/" className="font-semibold">
          Mini-Rayyan
        </Link>
        <Link href="/">Queries</Link>
        <Link href="/records">Records</Link>
        <button
          className="ml-auto text-neutral-500 hover:underline"
          onClick={() => {
            setToken(null);
            router.push("/login");
          }}
        >
          Sign out
        </button>
      </nav>
    </header>
  );
}
