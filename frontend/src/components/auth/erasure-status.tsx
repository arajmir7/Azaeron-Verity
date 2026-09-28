"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, type ErasureStatus } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, Notice } from "@/components/design-system";

export function ErasureReceipt() {
  const [id, setId] = useState("");
  const [receipt, setReceipt] = useState("");
  const [status, setStatus] = useState<ErasureStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    if (fragment.has("receipt")) {
      if (fragment.get("clear_session") === "1") useStore.getState().logout(true);
      // Synchronize the display-once receipt from the browser, then clear its URL.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setId(fragment.get("id") || "");
      setReceipt(fragment.get("receipt") || "");
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  async function refresh(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { setStatus(await api.getErasureStatus(id, receipt)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to check erasure."); }
    finally { setBusy(false); }
  }
  const input = "mt-2 w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm";
  return <main className="flex min-h-screen items-center justify-center bg-slate-50 px-5 py-10 dark:bg-slate-950"><section className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
    <h1 className="text-2xl font-semibold">Erasure status</h1>
    <p className="mt-3 text-sm">Save your request ID and receipt now. The receipt lets you check completion after your account is removed. It is kept only in this page’s memory.</p>
    {error && <div role="alert" className="mt-4"><Notice tone="danger">{error}</Notice></div>}
    <form onSubmit={refresh} className="mt-4 space-y-4"><label className="block text-sm font-semibold">Erasure request ID<input required autoComplete="off" value={id} onChange={(event) => { setId(event.target.value); setStatus(null); }} className={input} /></label><label className="block text-sm font-semibold">Erasure receipt<input required autoComplete="off" value={receipt} onChange={(event) => { setReceipt(event.target.value); setStatus(null); }} className={input} /></label><div className="flex flex-wrap gap-2"><Button type="submit" disabled={busy || !id || !receipt}>{busy ? "Checking…" : "Check erasure status"}</Button><Button variant="secondary" type="button" disabled={!id || !receipt} onClick={() => { const url = URL.createObjectURL(new Blob([`Azaeron erasure request\nID: ${id}\nReceipt: ${receipt}\nCheck: ${window.location.origin}/erasure-status\n`], { type: "text/plain" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "azaeron-erasure-receipt.txt"; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}>Save receipt</Button></div></form>
    <p role="status" className="mt-5 text-sm">{status ? status.status === "COMPLETED" ? "Erasure completed. Database removal and object deletion have been verified. Backup copies expire under the operator’s retention policy." : status.status === "FAILED" ? "Storage deletion has not been verified. The service will retry; retain this receipt." : `Erasure is in progress (${status.status.toLowerCase().replaceAll("_", " ")}). Allow at least eight minutes before completion and check again.` : "Enter your receipt and check the current status."}</p>
    <Link href="/login" className="mt-6 inline-block text-sm font-semibold text-teal-800 underline dark:text-teal-300">Return to sign in</Link>
  </section></main>;
}
