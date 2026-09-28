"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { Download, FileCheck2, FileText, GitBranch, History, Library, Quote, UserRoundSearch } from "lucide-react";
import { api, type AuthorshipSignal, type CitationAnalysis, type DocumentRecord, type EvidenceFirstReport, type EvidenceGraph, type ProvenanceTimeline } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, isPermissionError, LoadingState, ModuleNav, PageHeader, Panel, StatusBadge, DegradedBanner, Notice } from "@/components/design-system";

export type ModuleKind = "report" | "graph" | "sources" | "citations" | "authorship" | "provenance";
type ModuleData = EvidenceFirstReport | EvidenceGraph | CitationAnalysis | AuthorshipSignal | ProvenanceTimeline;

const copy: Record<ModuleKind, { eyebrow: string; title: string; description: string; icon: typeof FileText }> = {
  report: { eyebrow: "Evidence-led analysis", title: "Analysis report", description: "Seven independent dimensions with clear boundaries between production lineage, experimental signals, and missing evidence.", icon: FileCheck2 },
  graph: { eyebrow: "Traceability layer", title: "Evidence graph", description: "Navigate findings to exact text spans, evidence records, sources, citations, and claims.", icon: GitBranch },
  sources: { eyebrow: "Citation intelligence", title: "Sources", description: "Preserved source metadata and retrieval status. Source records are not treated as proof without supporting evidence.", icon: Library },
  citations: { eyebrow: "Citation intelligence", title: "Citations", description: "Claims, citations, references, and support findings in one auditable view.", icon: Quote },
  authorship: { eyebrow: "Consistency analysis", title: "Authorship consistency", description: "Statistical style comparison against an available baseline. This does not identify a person or make an accusation.", icon: UserRoundSearch },
  provenance: { eyebrow: "Document lineage", title: "Provenance", description: "Immutable versions, fingerprints, analysis runs, and events for the selected document.", icon: History },
};

async function fetchModule(kind: ModuleKind, documentId: string, versionId: string): Promise<ModuleData> {
  if (kind === "report") return api.getEvidenceFirstReport(documentId, versionId);
  if (kind === "graph") return api.getEvidenceGraph(documentId, versionId);
  if (kind === "sources" || kind === "citations") return api.getCitationAnalysis(documentId, versionId);
  if (kind === "authorship") return api.getAuthorshipAnalysis(documentId, versionId);
  const timeline = await api.getProvenanceTimeline(documentId);
  const version = timeline.versions.find((item) => item.id === versionId)!;
  return { ...timeline, document: { ...timeline.document, content_hash: version.content_hash, storage_object: version.storage_object },
    analysis_runs: timeline.analysis_runs.filter((item) => item.document_version_id === versionId),
    provenance_events: timeline.provenance_events.filter((item) => item.document_version_id === versionId) };

}

function confidenceText(value: number | null | undefined) {
  return value == null ? "Unavailable" : `Recorded for review · ${Math.round(value * 100)}%`;
}

export function ModulePage({ kind }: { kind: ModuleKind }) {
  const { currentOrg } = useStore();
  const searchParams = useSearchParams();
  const requestedDocumentId = searchParams.get("document") || "";
  const requestedVersion = searchParams.get("version") || "";
  const router = useRouter();
  const pathname = usePathname();
  const [versions, setVersions] = useState<ProvenanceTimeline['versions']>([]);
  const [versionId, setVersionId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [data, setData] = useState<ModuleData | null>(null);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState("");
  const [permission, setPermission] = useState(false);
  const [exporting, setExporting] = useState(false);
  const spec = copy[kind];
  const Icon = spec.icon;
  const selectedDocument = useMemo(() => documents.find((document) => document.id === documentId), [documents, documentId]);

  useEffect(() => {
    if (!currentOrg) return;
    let active = true;
    void (async () => {
      setLoadingDocuments(true); setDocuments([]); setDocumentId(""); setData(null); setError(""); setPermission(false);
      try {
        const response = await api.getDocuments();
        const items = response.items || [];
        const requested = requestedDocumentId ? await api.getDocument(requestedDocumentId) : items[0];
        if (!active) return;
        setDocuments(requested && !items.some((item) => item.id === requested.id) ? [requested, ...items] : items);
        setDocumentId(requested?.id || "");
      } catch (reason) {
        if (active) { setError(reason instanceof Error ? reason.message : "Unable to load documents."); setPermission(isPermissionError(reason)); }
      } finally { if (active) setLoadingDocuments(false); }
    })();
    return () => { active = false; };
  }, [currentOrg, requestedDocumentId]);

  useEffect(() => {
    if (!documentId || !currentOrg) return;
    let active = true;
    void (async () => {
      setLoadingData(true); setData(null); setError(""); setPermission(false);
      try {
        const timeline = await api.getProvenanceTimeline(documentId);
        const version = requestedVersion || timeline.versions.at(-1)?.id;
        if (!version || !timeline.versions.some((item) => item.id === version)) throw new Error("Document version not found");
        const result = await fetchModule(kind, documentId, version);
        if (active) { setVersions(timeline.versions); setVersionId(version); setData(result); }
      } catch (reason) {
        if (active) { setError(reason instanceof Error ? reason.message : "Unable to load this analysis."); setPermission(isPermissionError(reason)); }
      } finally { if (active) setLoadingData(false); }
    })();
    return () => { active = false; };
  }, [documentId, kind, currentOrg, requestedVersion]);

  const exportHistory = async () => {
    if (!documentId) return;
    setExporting(true);
    try { await api.exportProvenance(documentId); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to export provenance history."); } finally { setExporting(false); }
  };

  const retry = () => { window.location.reload(); };
  return <div><DegradedBanner /><PageHeader eyebrow={spec.eyebrow} title={spec.title} description={spec.description} action={kind === "provenance" && documentId ? <Button variant="secondary" onClick={() => void exportHistory()} disabled={exporting}><Download size={16} aria-hidden="true" /> {exporting ? "Preparing…" : "Export history"}</Button> : undefined} />
    {loadingDocuments ? <LoadingState label="Loading document context…" rows={4} /> : permission ? <ErrorState permission message="Your role cannot access this workspace analysis." onRetry={retry} /> : error && !data ? <ErrorState message={error} onRetry={retry} /> : documents.length === 0 ? <EmptyState icon={Icon} title={kind === "report" ? "Run an analysis to view supporting evidence" : `No ${spec.title.toLowerCase()} yet`} description="Create or open a document to view its recorded analysis here." action={<Link href="/check"><Button><FileText size={16} aria-hidden="true" /> Upload document</Button></Link>} /> : <>
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"><label className="min-w-[220px] flex-1 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Document<select aria-label="Document for this analysis" value={documentId} onChange={(event) => router.replace(`${pathname}?document=${event.target.value}`, { scroll: false })} className="mt-2 block w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-semibold normal-case tracking-normal text-slate-900 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 dark:border-slate-700 dark:bg-slate-950 dark:text-white">{documents.map((document) => <option key={document.id} value={document.id}>{document.title || document.original_filename}</option>)}</select></label><div className="text-xs text-slate-500">{selectedDocument?.status || ""} · version-scoped evidence</div></div>
      <label className="mb-4 block text-sm font-semibold">Document version<select aria-label="Module document version" value={versionId} onChange={(event) => router.replace(`${pathname}?document=${documentId}&version=${event.target.value}`, { scroll: false })} className="ml-3 rounded-lg border bg-transparent px-3 py-2">{versions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number}</option>)}</select></label>
      <ModuleNav documentId={documentId} versionId={versionId} />
      {loadingData ? <LoadingState label={`Loading ${spec.title.toLowerCase()}…`} rows={5} /> : error ? <ErrorState message={error} onRetry={retry} /> : data && renderModule(kind, data)}
    </>}
  </div>;
}

function renderModule(kind: ModuleKind, data: ModuleData): ReactNode {
  if (kind === "report") return <ReportContent report={data as EvidenceFirstReport} />;
  if (kind === "graph") return <GraphContent graph={data as EvidenceGraph} />;
  if (kind === "sources") return <SourcesContent analysis={data as CitationAnalysis} />;
  if (kind === "citations") return <CitationsContent analysis={data as CitationAnalysis} />;
  if (kind === "authorship") return <AuthorshipContent signal={data as AuthorshipSignal} />;
  return <ProvenanceContent timeline={data as ProvenanceTimeline} />;
}

function ReportContent({ report }: { report: EvidenceFirstReport }) {
  return <div className="space-y-5"><Notice tone="neutral"><strong>How to read this report.</strong> These dimensions describe recorded evidence. They do not produce a single AI percentage or establish who wrote a document.</Notice><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{report.dimensions.map((dimension) => <Panel key={dimension.key} title={dimension.label} action={<StatusBadge status={dimension.status} />}><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{dimension.summary}</p><div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-950/60"><p className="font-semibold text-slate-700 dark:text-slate-200">Confidence</p><p className="mt-1 text-slate-500">{confidenceText(dimension.confidence)} · {dimension.confidence_reliability}</p></div><p className="mt-4 text-xs leading-5 text-slate-500"><strong>Recommended action:</strong> {dimension.recommended_action}</p><details className="mt-4 text-xs text-slate-500"><summary className="cursor-pointer font-semibold">Limitations ({dimension.limitations.length})</summary><ul className="mt-2 space-y-1">{dimension.limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}</ul></details></Panel>)}</div><Panel eyebrow="Exact spans" title="Highlighted findings" description="Only spans recorded by the analysis pipeline are shown; missing spans are not inferred.">{report.highlights.length ? <div className="space-y-3">{report.highlights.slice(0, 50).map((highlight) => <article key={highlight.evidence_node_id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="flex flex-wrap justify-between gap-2"><span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">{highlight.dimension.replaceAll("_", " ")} · {highlight.segment_type}</span><StatusBadge status={highlight.status} /></div><p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-800 dark:bg-slate-950/60 dark:text-slate-200">“{highlight.span_text}” <span className="text-xs text-slate-500">({highlight.span_start}–{highlight.span_end})</span></p><p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-400">{highlight.explanation}</p><p className="mt-2 text-xs text-slate-500">Evidence {highlight.evidence_node_id} · {highlight.source_titles.length ? `Source: ${highlight.source_titles.join(" · ")}` : "No source recorded"}</p></article>)}</div> : <EmptyState title="No exact highlights" description="No sentence or paragraph finding with a recorded span is available for this document version." />}</Panel></div>;
}

function GraphContent({ graph }: { graph: EvidenceGraph }) {
  return <div className="space-y-5"><div className="grid gap-4 sm:grid-cols-3"><Panel title="Nodes"><p className="text-3xl font-semibold text-slate-950 dark:text-white">{graph.nodes.length}</p><p className="mt-1 text-xs text-slate-500">Canonical evidence records</p></Panel><Panel title="Relationships"><p className="text-3xl font-semibold text-slate-950 dark:text-white">{graph.edges.length}</p><p className="mt-1 text-xs text-slate-500">Traceable graph edges</p></Panel><Panel title="Integrity" action={<StatusBadge status={graph.complete ? "PRODUCTION" : "INCOMPLETE"} />}><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{graph.orphan_finding_node_ids.length ? `${graph.orphan_finding_node_ids.length} orphan finding(s) require attention.` : "No orphan findings were reported."}</p></Panel></div><Panel eyebrow="Inspectable records" title="Evidence graph nodes" description="The graph is tenant-scoped and tied to an immutable document version."><div className="space-y-2">{graph.nodes.slice(0, 100).map((node) => <div key={node.node_id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={node.canonical_type} tone="neutral" /><p className="font-semibold text-slate-900 dark:text-white">{node.title}</p></div><p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">{node.description || "No explanation recorded."}</p>{node.span_text && <p className="mt-2 rounded bg-slate-50 p-2 text-xs text-slate-700 dark:bg-slate-950/60 dark:text-slate-300">“{node.span_text}”</p>}</div><span className="font-mono text-[10px] text-slate-600">{node.node_id}</span></div>)}</div></Panel></div>;
}

function SourcesContent({ analysis }: { analysis: CitationAnalysis }) {
  return <Panel eyebrow="Preserved metadata" title={`${analysis.sources.length} source${analysis.sources.length === 1 ? "" : "s"}`} description="Retrieval status and metadata are shown as recorded. No source content is fabricated.">{analysis.sources.length ? <div className="grid gap-3 lg:grid-cols-2">{analysis.sources.map((source) => <article key={source.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold text-slate-900 dark:text-white">{source.title || "Untitled source"}</h2><p className="mt-1 text-sm text-slate-500">{source.publisher || "Publisher not recorded"}</p></div><StatusBadge status={source.retrieval_status} /></div><dl className="mt-4 grid gap-2 text-xs text-slate-500"><div><dt className="inline font-semibold">DOI: </dt><dd className="inline">{source.doi || "not recorded"}</dd></div><div><dt className="inline font-semibold">URL: </dt><dd className="inline break-all">{source.url || "not recorded"}</dd></div><div><dt className="inline font-semibold">Retrieved: </dt><dd className="inline">{source.retrieval_timestamp || "not recorded"}</dd></div></dl></article>)}</div> : <EmptyState icon={Library} title="No source records" description="Sources will appear when citation analysis records real source metadata." />}</Panel>;
}

function CitationsContent({ analysis }: { analysis: CitationAnalysis }) {
  return <div className="space-y-5"><div className="grid gap-4 sm:grid-cols-3"><Panel title="Citations"><p className="text-3xl font-semibold text-slate-950 dark:text-white">{analysis.citations.length}</p><p className="mt-1 text-xs text-slate-500">Recorded citation spans</p></Panel><Panel title="References"><p className="text-3xl font-semibold text-slate-950 dark:text-white">{analysis.references.length}</p><p className="mt-1 text-xs text-slate-500">Reference records</p></Panel><Panel title="Findings"><p className="text-3xl font-semibold text-slate-950 dark:text-white">{analysis.findings.length}</p><p className="mt-1 text-xs text-slate-500">Auditable support findings</p></Panel></div><Panel eyebrow="Claim support" title="Citation findings">{analysis.findings.length ? <div className="space-y-3">{analysis.findings.map((finding) => <article key={finding.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">{finding.finding_type.replaceAll("_", " ")}</span><StatusBadge status={finding.support_status} /></div><p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-300">{finding.message}</p><p className="mt-2 text-xs text-slate-500">Claim {finding.claim_id || "not linked"} · Citation {finding.citation_id || "not linked"} · Source {finding.source_id || "not linked"}</p></article>)}</div> : <EmptyState icon={Quote} title="No citation findings" description="No citation support findings were recorded for this document version." />}</Panel></div>;
}

function AuthorshipContent({ signal }: { signal: AuthorshipSignal }) {
  return <div className="space-y-5"><Notice tone="warning"><strong>Interpretation boundary.</strong> This is a statistical style comparison against a baseline. It does not identify a person, establish misconduct, or replace human review.</Notice><Panel eyebrow="Baseline comparison" title="Consistency result" action={<StatusBadge status={signal.verdict} />}><div className="grid gap-4 sm:grid-cols-3"><div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-950/60"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Baseline quality</p><p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{signal.baseline_quality || "Unavailable"}</p></div><div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-950/60"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Data confidence</p><p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{confidenceText(signal.confidence)}</p></div><div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-950/60"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">AI-writing signal</p><p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">Separate dimension</p></div></div><p className="mt-5 text-sm leading-6 text-slate-600 dark:text-slate-300">{signal.explanation || "No explanation was recorded."}</p><p className="mt-3 text-xs leading-5 text-slate-500">{signal.limitations || "Limitations were not recorded."}</p></Panel></div>;
}

function ProvenanceContent({ timeline }: { timeline: ProvenanceTimeline }) {
  return <div className="space-y-5"><Panel eyebrow="Immutable lineage" title="Document fingerprint" action={<StatusBadge status="PRODUCTION" />}><dl className="grid gap-4 sm:grid-cols-2"><div><dt className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Content hash</dt><dd className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">{timeline.document.content_hash}</dd></div><div><dt className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">Storage object</dt><dd className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">{timeline.document.storage_object}</dd></div></dl></Panel><Panel eyebrow="Version history" title={`${timeline.versions.length} immutable version${timeline.versions.length === 1 ? "" : "s"}`}><div className="space-y-3">{timeline.versions.map((version) => <article key={version.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold text-slate-900 dark:text-white">Version {version.version_number}</span><StatusBadge status={version.lifecycle_state} /></div><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{version.change_summary || "No change summary recorded."}</p><p className="mt-2 break-all font-mono text-[10px] text-slate-500">SHA-256 {version.sha256_fingerprint}</p></article>)}</div></Panel><Panel eyebrow="Events" title="Analysis and provenance events"><div className="space-y-3">{timeline.provenance_events.map((event) => <div key={event.id} className="flex gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-teal-600" /><div><p className="text-sm font-semibold text-slate-900 dark:text-white">{event.event_type}</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{event.description || "No description recorded."}</p><p className="mt-2 text-xs text-slate-500">{event.event_timestamp || "Timestamp unavailable"}</p></div></div>)}{!timeline.provenance_events.length && <EmptyState icon={History} title="No events recorded" description="The document has no provenance events available for display." />}</div></Panel></div>;
}
