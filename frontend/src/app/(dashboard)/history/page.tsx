"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { DocumentReceipts } from "@/components/verity-receipts";
import { ArrowUpRight, History } from "lucide-react";
import { api, type DocumentRecord, type ProvenanceTimeline } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, Panel } from "@/components/design-system";

type RecentDocument = { document: DocumentRecord; versions: ProvenanceTimeline["versions"] | null };

export default function HistoryPage() {
  const { currentOrg } = useStore();
  const [items, setItems] = useState<RecentDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    if (!currentOrg) return;
    setLoading(true); setError("");
    try {
      const list = await api.getDocuments();
      const recent = list.items.slice(0, 10);
      const timelines = await Promise.allSettled(recent.map((document) => api.getProvenanceTimeline(document.id)));
      setItems(recent.map((document, index) => ({ document, versions: timelines[index].status === "fulfilled" ? timelines[index].value.versions : null })));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load history."); }
    finally { setLoading(false); }
  }, [currentOrg]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, [load]);
  return <div className="mx-auto max-w-5xl"><PageHeader eyebrow="History" title="Your recent work" description="Return to a document or inspect its saved versions. This list contains actual workspace records." />
    {loading ? <LoadingState label="Loading history…" /> : error ? <ErrorState message={error} onRetry={() => void load()} /> : !items.length ? <EmptyState icon={History} title="No history yet" description="Create or import a document. Saved revisions will appear here." action={<Link href="/check?next=editor"><Button>Create document</Button></Link>} /> : <Panel title="Recent documents"><ul className="divide-y divide-slate-100 dark:divide-slate-800">{items.map(({ document, versions }) => <li key={document.id} className="flex flex-wrap items-center gap-3 py-4"><History size={17} className="text-teal-800" aria-hidden="true" /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{document.title || document.original_filename}</p><p className="mt-1 text-xs text-slate-500">{versions ? `${versions.length} saved version${versions.length === 1 ? "" : "s"}` : "Version history unavailable"} · {new Date(document.updated_at || document.created_at).toLocaleDateString()}</p></div><Link href={`/write?document=${document.id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-teal-800 dark:text-teal-300">Open <ArrowUpRight size={14} aria-hidden="true" /></Link><Link href={`/provenance?document=${document.id}`} className="text-xs font-semibold text-slate-600 hover:text-teal-800">Version details</Link><div className="w-full"><DocumentReceipts documentId={document.id} /></div></li>)}</ul></Panel>}
  </div>;
}
