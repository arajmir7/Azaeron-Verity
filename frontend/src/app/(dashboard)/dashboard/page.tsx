"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, BookOpen, CheckCircle2, Clock3, FileCheck2, FileText, PenLine, UploadCloud } from "lucide-react";
import { api, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, isPermissionError, LoadingState, PageHeader, Panel, StatusBadge, WorkflowCard, WorkspaceSetup } from "@/components/design-system";

type DashboardState = "loading" | "success" | "empty" | "error" | "permission";

const workflows = [
  { step: "01 · Check", icon: UploadCloud, title: "Check a document", outcome: "Create a trustworthy starting point", detail: "Paste, type, or upload a document. AZAERON fingerprints the version before available analyses begin.", href: "/check" },
  { step: "02 · Review", icon: FileCheck2, title: "Review the evidence", outcome: "Move from findings to a human decision", detail: "Open exact spans, sources, citations, signal limitations, and provenance in one document context.", href: "/documents" },
  { step: "03 · Write", icon: PenLine, title: "Improve a draft", outcome: "Make visible, reversible editorial changes", detail: "Compare original and revision, review each reason, and preserve the change ledger for the document.", href: "/write" },
  { step: "04 · Research", icon: BookOpen, title: "Strengthen source support", outcome: "Connect claims to real references", detail: "Inspect citation support, reference metadata, source quality, and unresolved evidence gaps.", href: "/citations" },
];

export default function DashboardPage() {
  const { user, currentOrg } = useStore();
  const [state, setState] = useState<DashboardState>("loading");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    if (!currentOrg) return;
    setState("loading");
    setError("");
    try {
      const response = await api.getDocuments(1);
      const items = response.items || [];
      setDocuments(items.slice(0, 5));
      setTotal(response.total);
      setState(items.length ? "success" : "empty");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load workspace data.");
      setState(isPermissionError(reason) ? "permission" : "error");
    }
  }, [currentOrg]);

  // The effect synchronizes this page with the authenticated API.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadData(); }, [loadData]);

  const processing = documents.filter((document) => document.status === "processing" || document.status === "queued").length;
  const completed = documents.filter((document) => document.status === "completed").length;
  const failed = documents.filter((document) => document.status === "failed").length;
  const displayName = user?.first_name || user?.email?.split("@")[0] || "there";

  return <div>
    <PageHeader eyebrow="Workspace home" title={`Move from draft to defensible decision, ${displayName}.`} description={currentOrg ? `${currentOrg.name} · one evidence-first workspace for checking, reviewing, writing, and research` : "Select a workspace to view tenant-scoped evidence."} action={<div className="flex flex-wrap gap-2"><Link href="/write"><Button variant="secondary"><PenLine size={16} aria-hidden="true" /> Open Write</Button></Link><Link href="/check"><Button><UploadCloud size={16} aria-hidden="true" /> Start a check</Button></Link></div>} />
    {!currentOrg ? <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,.9fr)]"><WorkspaceSetup /><Panel eyebrow="Why a workspace?" title="A clear boundary for every decision"><div className="space-y-4 text-sm leading-6 text-slate-600 dark:text-slate-300"><p>Documents, analysis runs, sources, and provenance stay together inside a tenant-scoped workspace.</p><div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1"><div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800"><p className="font-semibold text-slate-900 dark:text-white">Private by default</p><p className="mt-1 text-xs text-slate-500">Only authorized members can access records.</p></div><div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800"><p className="font-semibold text-slate-900 dark:text-white">Version-aware</p><p className="mt-1 text-xs text-slate-500">Every review stays attached to its source version.</p></div><div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800"><p className="font-semibold text-slate-900 dark:text-white">Evidence-first</p><p className="mt-1 text-xs text-slate-500">Missing evidence is shown instead of guessed.</p></div></div></div></Panel></div> : state === "loading" ? <LoadingState label="Loading workspace overview…" rows={4} /> : state === "permission" ? <ErrorState permission message="Your current role cannot read this workspace. Ask a workspace administrator to grant access." onRetry={() => void loadData()} /> : state === "error" ? <ErrorState message={error} onRetry={() => void loadData()} /> : <>
      <Panel eyebrow="One workspace · four outcomes" title="Choose the job you need to do" description="The workflow changes the next action; the same document, evidence, and provenance remain connected underneath.">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{workflows.map((workflow) => <WorkflowCard key={workflow.step} {...workflow} />)}</div>
      </Panel>

      <div className="my-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[{ label: "Documents in workspace", value: total, icon: FileText, tone: "text-teal-800" }, { label: "In progress · recent view", value: processing, icon: Clock3, tone: "text-amber-700" }, { label: "Ready to inspect · recent view", value: completed, icon: CheckCircle2, tone: "text-emerald-700" }, { label: "Needs attention · recent view", value: failed, icon: FileCheck2, tone: "text-rose-700" }].map((card) => { const Icon = card.icon; return <div key={card.label} className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-[0_18px_55px_-38px_rgba(15,23,42,0.38)] dark:border-slate-800 dark:bg-slate-900"><div className="flex items-center justify-between"><span className={`grid h-9 w-9 place-items-center rounded-xl bg-slate-50 ${card.tone} dark:bg-slate-950`}><Icon size={17} aria-hidden="true" /></span>{card.label === "Documents in workspace" && <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-600">Live</span>}</div><p className="mt-5 text-3xl font-semibold tracking-[-0.04em] text-slate-950 dark:text-white">{card.value === null ? "—" : card.value}</p><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{card.label}</p></div>; })}
      </div>

      <Panel eyebrow="Continue where you left off" title="Recent documents" description="Open a document to inspect its immutable version, evidence, and available analyses." action={<Link href="/documents" className="inline-flex items-center gap-1 text-sm font-semibold text-teal-800 hover:text-teal-950 dark:text-teal-300">Open review queue <ArrowUpRight size={15} aria-hidden="true" /></Link>}>
        {state === "empty" ? <EmptyState icon={FileText} title="No documents yet" description="Upload a document to create its first immutable version and start evidence collection." action={<Link href="/check"><Button variant="secondary"><UploadCloud size={16} aria-hidden="true" /> Upload your first document</Button></Link>} /> : <div className="divide-y divide-slate-100 dark:divide-slate-800">{documents.map((document) => <Link key={document.id} href={`/documents/${document.id}`} className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0 hover:bg-slate-50/70 dark:hover:bg-slate-800/30"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{document.title || document.original_filename}</p><p className="mt-1 text-xs text-slate-500">{new Date(document.created_at).toLocaleDateString()} · {document.original_filename}</p></div><StatusBadge status={document.status} /></Link>)}</div>}
      </Panel>

      <div className="mt-6 grid gap-4 lg:grid-cols-2"><Panel eyebrow="Interpretation" title="Evidence before conclusion"><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">AZAERON separates originality, similarity, AI-writing signals, authorship consistency, citation integrity, source quality, and provenance. A missing or unvalidated analysis remains visible as insufficient evidence.</p><Link href="/reports" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-teal-800 dark:text-teal-300">Open an analysis report <ArrowUpRight size={15} /></Link></Panel><Panel eyebrow="Responsible writing" title="Improve without hiding lineage"><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">AZAERON Write is for better writing, not detector bypass. Every supported editorial suggestion keeps the original, revision, and reason together.</p><Link href="/write" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-teal-800 dark:text-teal-300">Open the change ledger <ArrowUpRight size={15} /></Link></Panel></div>
    </>}
  </div>;
}
