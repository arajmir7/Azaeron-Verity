"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, FileCheck2, FileText, PenLine, ScanSearch, Sparkles } from "lucide-react";
import { api, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, ErrorState, isPermissionError, LoadingState, StatusBadge } from "@/components/design-system";

type DashboardState = "loading" | "ready" | "error" | "permission";

const actions = [
  { href: "/ai", label: "Ask Azaeron AI", detail: "Private AI pending approval", icon: Sparkles },
  { href: "/humaniser", label: "Humanise text", detail: "Review changes to your writing", icon: PenLine },
  { href: "/detector", label: "Detect AI", detail: "Inspect experimental writing signals", icon: ScanSearch },
  { href: "/plagiarism", label: "Check plagiarism", detail: "Compare with available sources", icon: FileCheck2 },
  { href: "/write", label: "Open document", detail: "Edit and preserve your versions", icon: FileText },
];

export default function DashboardPage() {
  const { user, currentOrg } = useStore();
  const [state, setState] = useState<DashboardState>("loading");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    if (!currentOrg) return;
    setState("loading");
    setError("");
    try {
      const response = await api.getDocuments(1);
      setDocuments((response.items || []).slice(0, 5));
      setState("ready");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load your documents.");
      setState(isPermissionError(reason) ? "permission" : "error");
    }
  }, [currentOrg]);

  // The effect synchronizes this page with the authenticated API.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadData(); }, [loadData]);

  const displayName = user?.first_name || user?.email?.split("@")[0] || "there";
  const reports = documents.filter((document) => document.status === "completed").slice(0, 3);

  return <div className="mx-auto max-w-6xl space-y-8">
    <header className="rounded-3xl bg-teal-950 px-6 py-9 text-white sm:px-9 sm:py-11">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-200">Hello, {displayName}</p>
      <h1 className="mt-3 max-w-2xl text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Write better. Check confidently. Understand your work.</h1>
      <p className="mt-3 max-w-xl text-sm leading-6 text-teal-100/80">One place to work on a draft, inspect writing signals, and review matches with sources you can see.</p>
      <Link href="/ai" className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-teal-950 hover:bg-teal-50">View Azaeron AI <ArrowUpRight size={16} aria-hidden="true" /></Link>
    </header>

    <section aria-labelledby="start-title">
      <h2 id="start-title" className="text-lg font-semibold text-slate-950 dark:text-white">What would you like to do?</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{actions.map(({ href, label, detail, icon: Icon }) => <Link key={href} href={href} className="group flex min-h-28 items-start gap-4 rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-teal-400 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-600/40 dark:border-slate-800 dark:bg-slate-900"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-900 dark:bg-teal-950 dark:text-teal-200"><Icon size={19} aria-hidden="true" /></span><span><span className="block text-sm font-semibold text-slate-950 dark:text-white">{label}</span><span className="mt-1 block text-xs leading-5 text-slate-500 dark:text-slate-400">{detail}</span></span><ArrowUpRight size={15} className="ml-auto shrink-0 text-slate-400 group-hover:text-teal-800" aria-hidden="true" /></Link>)}</div>
    </section>

    {state === "loading" ? <LoadingState label="Loading your recent work…" rows={3} /> : state === "permission" ? <ErrorState permission message="Your role cannot read documents in this workspace." onRetry={() => void loadData()} /> : state === "error" ? <ErrorState message={error} onRetry={() => void loadData()} /> : <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <section aria-labelledby="recent-documents" className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><div className="flex items-center justify-between gap-3"><h2 id="recent-documents" className="text-base font-semibold">Recent documents</h2><Link href="/documents" className="text-xs font-semibold text-teal-800 dark:text-teal-300">View all</Link></div>{documents.length ? <ul className="mt-4 divide-y divide-slate-100 dark:divide-slate-800">{documents.map((document) => <li key={document.id} className="flex items-center gap-3 py-3"><FileText size={17} className="shrink-0 text-teal-800" aria-hidden="true" /><Link href={`/write?document=${document.id}`} className="min-w-0 flex-1 truncate text-sm font-medium hover:text-teal-800">{document.title || document.original_filename}</Link><StatusBadge status={document.status} /></li>)}</ul> : <div className="mt-4 rounded-xl border border-dashed border-slate-300 px-5 py-6 text-center dark:border-slate-700"><p className="text-sm font-semibold">No documents yet</p><p className="mt-2 text-xs text-slate-500">Create a draft or import a file to get started.</p><Link href="/check" className="mt-4 inline-block"><Button variant="secondary">Create document</Button></Link></div>}</section>
      <div className="space-y-5"><section aria-labelledby="recent-reports" className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 id="recent-reports" className="text-base font-semibold">Recent reports</h2>{reports.length ? <ul className="mt-3 space-y-2">{reports.map((document) => <li key={document.id}><Link href={`/documents/${document.id}`} className="flex items-center gap-2 rounded-lg py-2 text-sm font-medium hover:text-teal-800"><FileCheck2 size={16} aria-hidden="true" /><span className="truncate">{document.title || document.original_filename}</span><ArrowUpRight size={14} className="ml-auto shrink-0" aria-hidden="true" /></Link></li>)}</ul> : <p className="mt-3 text-sm leading-6 text-slate-500">Reports appear here after a document finishes processing.</p>}</section><section aria-labelledby="recent-chats" className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 id="recent-chats" className="text-base font-semibold">Recent chats</h2><p className="mt-3 text-sm leading-6 text-slate-500">Chat history will appear when private AI is available. No conversations are recorded yet.</p></section></div>
    </div>}
  </div>;
}
