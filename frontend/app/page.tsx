"use client";

import { useEffect, useState } from "react";
import { api, type Reviewer } from "@/lib/api";

export default function Home() {
  const [me, setMe] = useState<Reviewer | null>(null);
  useEffect(() => {
    api.me().then(setMe).catch(() => {});
  }, []);
  return <p>{me ? `Signed in as ${me.name}` : "Loading…"}</p>;
}
