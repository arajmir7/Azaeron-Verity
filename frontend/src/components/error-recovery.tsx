"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { reportBrowserError } from "@/lib/telemetry";

export function ErrorRecovery({ retry }: { retry: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
    reportBrowserError("render");
  }, []);
  return (
    <main style={{ maxWidth: "40rem", margin: "4rem auto", padding: "1.5rem" }}>
      <h1 ref={heading} tabIndex={-1}>This page could not load</h1>
      <p>Your saved documents are still available. Try loading the page again.</p>
      <button type="button" onClick={retry} style={{ padding: "0.75rem 1rem", marginTop: "1rem" }}>Try again</button>
      <p><Link href="/documents">Go to documents</Link></p>
    </main>
  );
}
