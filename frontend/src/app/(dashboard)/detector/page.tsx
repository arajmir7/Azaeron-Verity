"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { DocumentIntake } from "@/components/document-intake";
import { useSearchParams } from "next/navigation";
import { AlertCircle, ArrowUpRight, FileText, ScanSearch } from "lucide-react";
import { api, type DetectionResult, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, LoadingState, Notice, PageHeader, Panel, StatusBadge } from "@/components/design-system";

const verdicts: Record<string, string> = {
  human: "Likely human", ai_generated: "Likely AI-generated", ai: "Likely AI-generated",
  mixed: "Mixed / AI-assisted", ai_assisted: "Mixed / AI-assisted",
  uncertain: "Uncertain", insufficient_evidence: "Insufficient evidence",
};

export default function DetectorPage() {
  const { currentOrg } = useStore();
  const requestedDocument = useSearchParams().get("document") || "";
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");

  const loadDocuments = useCallback(async () => {
    if (!currentOrg) return;
    setLoading(true); setError("");
    try {
      const list = await api.getDocuments();
      const selected = requestedDocument ? await api.getDocument(requestedDocument) : list.items[0];
      setDocuments(selected && !list.items.some((item) => item.id === selected.id) ? [selected, ...list.items] : list.items);
      setDocumentId(selected?.id || "");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load documents."); }
    finally { setLoading(false); }
  }, [currentOrg, requestedDocument]);

  // Read only the active workspace's documents.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadDocuments(); }, [loadDocuments]);

  useEffect(() => {
    if (!currentOrg || !documentId) return;
    let active = true;
    void (async () => {
      setChecking(true); setError(""); setResult(null);
      try { const response = await api.getDetectionResult(documentId); if (active) setResult(response); }
      catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Analysis is not available for this document yet."); }
      finally { if (active) setChecking(false); }
    })();
    return () => { active = false; };
  }, [currentOrg, documentId]);

  return <div className="mx-auto max-w-5xl"><PageHeader eyebrow="AI Detector" title="Review writing signals" description="Inspect available evidence and its limits. A detector cannot establish who wrote a text or decide misconduct." action={<Link href="/check?next=detector"><Button><ScanSearch size={16} aria-hidden="true" /> Check new text</Button></Link>} />
    <DocumentIntake onReady={(attachment) => { void api.getDocuments().then((list) => setDocuments(list.items)); setDocumentId(attachment.document_id); }} />
    <Notice tone="warning"><strong>Experimental.</strong> This detector has not passed production calibration. It abstains when reliable authorship assessment is unavailable; no unvalidated percentage is shown.</Notice>
    <div className="mt-5">{loading ? <LoadingState label="Loading documents…" /> : error && !documentId ? <ErrorState message={error} onRetry={() => void loadDocuments()} /> : !documents.length ? <EmptyState icon={FileText} title="Paste text or choose a document to analyse" description="Create a private document first, then review its available writing signals." action={<Link href="/check?next=detector"><Button>Create document</Button></Link>} /> : <>
      <Panel title="Choose a document" className="mb-5"><label className="block max-w-lg text-sm font-semibold">Document<select aria-label="Document to check for AI" value={documentId} onChange={(event) => setDocumentId(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 dark:border-slate-700 dark:bg-slate-950">{documents.map((document) => <option key={document.id} value={document.id}>{document.title || document.original_filename}</option>)}</select></label></Panel>
      {checking ? <LoadingState label="Loading writing signals…" rows={2} /> : error ? <ErrorState title="Analysis not ready" message={error} /> : result ? <Panel title="Assessment" action={<StatusBadge status={result.release_status} />}><div className="flex items-start gap-3"><AlertCircle size={20} className="mt-1 shrink-0 text-amber-700" aria-hidden="true" /><div><p className="text-xl font-semibold text-slate-950 dark:text-white">{result.abstained ? "Uncertain" : verdicts[result.overall_verdict] || "Uncertain"}</p><p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{result.abstained ? result.abstention_reason || "Reliable authorship evidence is not available for this version." : result.explanation || "Review the supporting signals before reaching a decision."}</p></div></div>{result.limitations && <p className="mt-5 border-t border-slate-100 pt-4 text-sm leading-6 text-slate-500 dark:border-slate-800">{result.limitations}</p>}{result.segments.length > 0 && <details className="mt-5"><summary className="cursor-pointer text-sm font-semibold text-teal-900 dark:text-teal-200">Review recorded passages</summary><div className="mt-3 space-y-3">{result.segments.map((segment) => <div key={`${segment.segment_type}-${segment.segment_index}`} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{segment.segment_type} {segment.segment_index + 1} · {result.abstained ? "Uncertain" : verdicts[segment.verdict]}</p><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{segment.text}</p></div>)}</div></details>}<Link href={`/documents/${documentId}`} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-teal-800 dark:text-teal-300">Open document analysis <ArrowUpRight size={15} aria-hidden="true" /></Link></Panel> : null}
    </>}</div>
  </div>;
}
