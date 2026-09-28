"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, FileText, UploadCloud } from "lucide-react";
import { api, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, isPermissionError, LoadingState, PageHeader, Panel, StatusBadge } from "@/components/design-system";

export default function DocumentsPage() {
  const { currentOrg } = useStore();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permission, setPermission] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  const loadDocuments = useCallback(async () => {
    if (!currentOrg) { setLoading(false); setDocuments([]); setTotal(0); return; }
    setLoading(true); setError(""); setPermission(false);
    try {
      const response = await api.getDocuments(page);
      setDocuments(response.items || []); setTotal(response.total || 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load documents.");
      setPermission(isPermissionError(reason));
    } finally { setLoading(false); }
  }, [currentOrg, page]);

  // The effect synchronizes this page with the authenticated API.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadDocuments(); }, [loadDocuments]);
  const totalPages = Math.ceil(total / pageSize);
  const formatFileSize = (bytes: number) => bytes === 0 ? "0 B" : `${parseFloat((bytes / Math.pow(1024, Math.floor(Math.log(bytes) / Math.log(1024)))).toFixed(1))} ${["B", "KB", "MB", "GB"][Math.floor(Math.log(bytes) / Math.log(1024))]}`;

  return <div>
    <PageHeader eyebrow="Review · document queue" title="Review documents" description="Start with a document, then move through findings, exact spans, sources, citations, and provenance before making a human decision." action={<Link href="/check"><Button><UploadCloud size={16} aria-hidden="true" /> Check a document</Button></Link>} />
    <Panel title="Review queue" description={total ? `${total} document${total === 1 ? "" : "s"} in this workspace` : "No document records are available yet."}>
      {loading ? <LoadingState label="Loading document library…" rows={5} /> : permission ? <ErrorState permission message="Your role cannot read documents in this workspace." onRetry={() => void loadDocuments()} /> : error ? <ErrorState message={error} onRetry={() => void loadDocuments()} /> : documents.length === 0 ? <EmptyState icon={FileText} title="Your library is empty" description="Upload a PDF, DOCX, TXT, Markdown, or HTML document to begin. No sample statistics are shown until real workspace data exists." action={<Link href="/check"><Button variant="secondary"><UploadCloud size={16} aria-hidden="true" /> Upload your first document</Button></Link>} /> : <>
        <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left"><caption className="sr-only">Documents in the active workspace review queue</caption><thead><tr className="border-b border-slate-200 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500 dark:border-slate-800"><th className="pb-3 pr-4">Document</th><th className="pb-3 pr-4">Size</th><th className="pb-3 pr-4">Status</th><th className="pb-3 pr-4">Uploaded</th><th className="pb-3 text-right">Next action</th></tr></thead><tbody className="divide-y divide-slate-100 dark:divide-slate-800">{documents.map((document) => <tr key={document.id} className="group"><td className="py-4 pr-4"><p className="font-semibold text-slate-900 dark:text-white">{document.title || document.original_filename}</p><p className="mt-1 text-xs text-slate-500">{document.original_filename}</p></td><td className="py-4 pr-4 text-sm text-slate-600 dark:text-slate-400">{formatFileSize(document.file_size)}</td><td className="py-4 pr-4"><StatusBadge status={document.status} /></td><td className="py-4 pr-4 text-sm text-slate-600 dark:text-slate-400">{new Date(document.created_at).toLocaleDateString()}</td><td className="py-4 text-right">{document.status === "completed" ? <Link href={`/documents/${document.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-teal-800 hover:text-teal-950 dark:text-teal-300">Review evidence <ArrowUpRight size={15} /></Link> : <span className="text-xs text-slate-600">Available after processing</span>}</td></tr>)}</tbody></table></div>
        {totalPages > 1 && <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800"><Button variant="secondary" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page === 1}>Previous</Button><span className="text-xs font-medium text-slate-500">Page {page} of {totalPages}</span><Button variant="secondary" onClick={() => setPage((value) => Math.min(totalPages, value + 1))} disabled={page === totalPages}>Next</Button></div>}
      </>}
    </Panel>
  </div>;
}
