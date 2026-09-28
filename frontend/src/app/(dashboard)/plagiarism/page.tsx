"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight, FileCheck2 } from "lucide-react";
import { api, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, Panel } from "@/components/design-system";
import SimilarityPage from "../similarity/page";

export default function PlagiarismPage() {
  const documentId = useSearchParams().get("document") || "";
  const { currentOrg } = useStore();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!currentOrg || documentId) return;
    let active = true;
    void (async () => {
      setLoading(true); setError("");
      try { const list = await api.getDocuments(); if (active) setDocuments(list.items); }
      catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Unable to load documents."); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [currentOrg, documentId]);

  if (documentId) return <SimilarityPage />;
  return <div className="mx-auto max-w-5xl"><PageHeader eyebrow="Plagiarism Checker" title="Check text for matching sources" description="Compare your work with documents indexed in this workspace. Similarity is evidence for review, not a plagiarism verdict or an Internet-wide search." action={<Link href="/check?next=plagiarism"><Button><FileCheck2 size={16} aria-hidden="true" /> Check new text</Button></Link>} />
    {loading ? <LoadingState label="Loading documents…" /> : error ? <ErrorState message={error} /> : !documents.length ? <EmptyState icon={FileCheck2} title="Upload or paste content to check for matching text" description="The checker compares against available workspace sources and shows exactly what it found." action={<Link href="/check?next=plagiarism"><Button>Create document</Button></Link>} /> : <Panel title="Choose a document" description="Open a comparison to view matched passages, source coverage, and quotation exclusions."><ul className="divide-y divide-slate-100 dark:divide-slate-800">{documents.map((document) => <li key={document.id}><Link href={`/plagiarism?document=${encodeURIComponent(document.id)}`} className="flex items-center gap-3 py-4 text-sm font-semibold hover:text-teal-800"><FileCheck2 size={17} className="shrink-0 text-teal-800" aria-hidden="true" /><span className="min-w-0 flex-1 truncate">{document.title || document.original_filename}</span><ArrowUpRight size={15} className="shrink-0" aria-hidden="true" /></Link></li>)}</ul></Panel>}
  </div>;
}
