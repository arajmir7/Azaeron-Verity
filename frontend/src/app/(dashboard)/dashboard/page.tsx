"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, FileCheck2, FileText, MessageSquare, PenLine, Plus, ScanSearch, Sparkles } from "lucide-react";
import { api, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { EmptyState, ErrorState, isPermissionError, LoadingState, Panel, StatusBadge } from "@/components/design-system";

type Resource<T> = { value: T; state: "loading" | "ready" | "error" | "permission"; error?: string };
type Chat = { id: string; title: string };
const actions = [
  { href: "/ai", label: "Azaeron AI", detail: "Ask, explore and work with your documents.", icon: Sparkles },
  { href: "/humaniser", label: "AI Humaniser", detail: "Refine your writing. Keep your meaning.", icon: PenLine },
  { href: "/detector", label: "AI Detector", detail: "Inspect writing signals and uncertainty.", icon: ScanSearch },
  { href: "/plagiarism", label: "Plagiarism Checker", detail: "Find overlap with available sources.", icon: FileCheck2 },
  { href: "/documents", label: "Documents", detail: "Your drafts, versions and evidence.", icon: FileText },
];

export default function DashboardPage() {
  const { user, currentOrg } = useStore();
  const [documents, setDocuments] = useState<Resource<DocumentRecord[]>>({ value: [], state: "loading" });
  const [chats, setChats] = useState<Resource<Chat[]>>({ value: [], state: "loading" });
  const [models, setModels] = useState<Resource<number>>({ value: 0, state: "loading" });
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!currentOrg) return;
    let alive = true;
    const failure = (reason: unknown) => ({ state: isPermissionError(reason) ? "permission" as const : "error" as const, error: reason instanceof Error ? reason.message : "This information could not be loaded." });
    // Independent panels preserve useful results when another service is unavailable.
    void api.getDocuments(1).then((result) => { if (alive) setDocuments({ value: result.items.slice(0, 5), state: "ready" }); }).catch((reason) => { if (alive) setDocuments({ value: [], ...failure(reason) }); });
    void api.getConversations().then((result) => { if (alive) setChats({ value: result.items.slice(0, 4), state: "ready" }); }).catch((reason) => { if (alive) setChats({ value: [], ...failure(reason) }); });
    void api.getModels().then((result) => { if (alive) setModels({ value: result.models.length, state: "ready" }); }).catch((reason) => { if (alive) setModels({ value: 0, ...failure(reason) }); });
    return () => { alive = false; };
  }, [currentOrg, revision]);

  const displayName = user?.first_name || user?.email?.split("@")[0] || "there";
  const reports = documents.value.filter((document) => document.status === "completed").slice(0, 3);
  const linkStyle = "inline-flex min-h-10 items-center gap-2 text-sm font-semibold text-teal-800 hover:text-teal-950 dark:text-teal-300";
  return <div className="workspace-home space-y-7">
    <header className="home-intro">
      <div><p className="home-eyebrow">Your workspace, in focus</p><h1>Welcome back, {displayName}.</h1><p className="home-description">Good work starts with a clear draft. Pick up where you left off.</p></div>
      <Link href="/check" className="home-create"><Plus size={17} aria-hidden="true" /> Create document</Link>
    </header>
    <section aria-labelledby="start-title" className="home-tools">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 id="start-title" className="text-sm font-semibold text-slate-900 dark:text-white">Your writing toolkit</h2><span className="text-xs text-slate-600 dark:text-slate-400">Five tools. One connected workflow.</span></div>
      <div className="tool-grid">{actions.map(({ href, label, detail, icon: Icon }, index) => <Link key={href} href={href} className="tool-tile"><div className="flex items-center justify-between"><span className="tool-icon"><Icon size={20} aria-hidden="true" /></span><span className="tool-number" aria-hidden="true">0{index + 1}</span></div><h3>{label}</h3><p>{detail}</p><ArrowUpRight className="tool-arrow" size={17} aria-hidden="true" /></Link>)}</div>
      <div className="model-availability"><span className="availability-marker" aria-hidden="true" /><p>{models.state === "loading" ? "Checking model approval status…" : models.state !== "ready" ? "Model status could not be confirmed. Generation remains subject to approval checks." : models.value === 0 ? "AI generation is unavailable: no approved models are registered. You can still edit documents and review recorded evidence." : `${models.value} approved model${models.value === 1 ? "" : "s"} registered. Each request also checks task support and private runtime availability.`}</p>{models.state === "error" && <button onClick={retry} className="shrink-0 text-xs font-semibold underline">Retry status</button>}</div>
    </section>
    <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <Panel title="Recent documents" eyebrow="Continue your work" action={<Link href="/documents" className={linkStyle}>View all <ArrowRight size={14} aria-hidden="true" /></Link>}>
        {documents.state === "loading" ? <LoadingState label="Loading your recent work…" /> : documents.state !== "ready" ? <ErrorState permission={documents.state === "permission"} message={documents.error || "Unable to load documents."} onRetry={retry} /> : documents.value.length ? <ul className="document-list">{documents.value.map((document) => <li key={document.id}><span className="document-glyph"><FileText size={20} aria-hidden="true" /></span><div className="min-w-0 flex-1"><Link className="block truncate text-sm font-semibold hover:underline" href={document.status === "completed" ? `/write?document=${document.id}` : `/documents/${document.id}`}>{document.title || document.original_filename}</Link><p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{new Date(document.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</p></div><StatusBadge status={document.status} /></li>)}</ul> : <EmptyState title="A place for your next idea" description="Paste a draft or import a file. Your versions and review history stay together." action={<Link href="/check" className={linkStyle}>Create your first document <ArrowRight size={15} aria-hidden="true" /></Link>} />}
      </Panel>
      <Panel title="Recent chats" eyebrow="Pick up the conversation" action={<MessageSquare size={18} className="mt-3 text-slate-400" aria-hidden="true" />}>
        {chats.state === "loading" ? <LoadingState label="Loading conversations…" rows={2} /> : chats.state !== "ready" ? <ErrorState permission={chats.state === "permission"} message={chats.error || "Unable to load conversations."} onRetry={retry} /> : chats.value.length ? <ul className="chat-list">{chats.value.map((chat) => <li key={chat.id}><Link href={`/ai?conversation=${encodeURIComponent(chat.id)}`}><MessageSquare size={16} aria-hidden="true" /><span className="min-w-0 flex-1 truncate">{chat.title}</span><ArrowUpRight size={14} aria-hidden="true" /></Link></li>)}</ul> : <div className="py-5"><p className="text-sm font-medium">Your conversations start here.</p><p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">Saved conversations will appear here, including requests awaiting an approved model.</p></div>}
        <Link href="/ai" className={`${linkStyle} mt-3`}>Open Azaeron AI <ArrowRight size={14} aria-hidden="true" /></Link>
      </Panel>
    </div>
    <section aria-labelledby="recent-reports" className="home-reports"><div><span className="home-eyebrow">Evidence, within reach</span><h2 id="recent-reports" className="mt-2 text-lg font-semibold">Recent reports</h2><p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">Review the findings behind your writing.</p></div><div className="min-w-0 flex-1">{documents.state === "loading" ? <p className="text-sm text-slate-600 dark:text-slate-400">Loading reports…</p> : documents.state !== "ready" ? <p className="text-sm text-slate-600 dark:text-slate-400">Reports could not be loaded with your documents.</p> : reports.length ? <ul className="chat-list">{reports.map((document) => <li key={document.id}><Link href={`/documents/${document.id}`}><FileCheck2 size={17} aria-hidden="true" /><span className="min-w-0 flex-1 truncate">{document.title || document.original_filename}</span><ArrowUpRight size={14} aria-hidden="true" /></Link></li>)}</ul> : <p className="text-sm leading-6 text-slate-600 dark:text-slate-400">Reports appear here after a document finishes processing.</p>}</div></section>
  </div>;
}
