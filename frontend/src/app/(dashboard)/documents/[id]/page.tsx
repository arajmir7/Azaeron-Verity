"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useStore } from "@/lib/store";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowUpRight, Download, FileCheck2, FileText, Info, SlidersHorizontal } from "lucide-react";
import { api, type AuthorshipSignal, type CitationAnalysis, type DetectionExplainability, type DetectionResult, type DocumentContent, type DocumentRecord, type EvidenceFirstReport, type EvidenceGraph, type ProvenanceTimeline, type SimilarityMatch } from "@/lib/api";
import { Button, DegradedBanner, EmptyState, ErrorState, LoadingState, ModuleNav, Notice, PageHeader, Panel, StatusBadge, cn } from "@/components/design-system";

type ReportHighlight = EvidenceFirstReport["highlights"][number];

const HIGH_CONFIDENCE_THRESHOLD = 0.7;

const stateLabels: Record<string, string> = {
  human: "HUMAN",
  ai_generated: "AI",
  ai: "AI",
  mixed: "MIXED",
  ai_assisted: "AI_ASSISTED",
  uncertain: "UNCERTAIN",
  insufficient_evidence: "INSUFFICIENT_EVIDENCE",
};

function formatBytes(bytes?: number) {
  if (!bytes) return "Not recorded";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value?: string | null) {
  if (!value) return "Not recorded";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function confidenceLabel(value: number | null | undefined, reliability?: string) {
  if (value == null) return "Not recorded";
  return `${Math.round(value * 100)}% recorded confidence${reliability ? ` · ${reliability}` : ""}`;
}

function stateClass(state: string) {
  if (state === "HUMAN") return "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300";
  if (state === "AI" || state === "AI_ASSISTED") return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300";
  if (state === "MIXED") return "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-900/60 dark:bg-indigo-950/30 dark:text-indigo-300";
  return "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300";
}

function FindingCard({ finding, selected, onSelect }: { finding: ReportHighlight; selected: boolean; onSelect: () => void }) {
  return <article id={`finding-${finding.evidence_node_id}`} className={cn("scroll-mt-6 rounded-xl border transition", selected ? "border-teal-500 bg-teal-50/50 shadow-sm dark:border-teal-700 dark:bg-teal-950/20" : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900")}>
    <button type="button" onClick={onSelect} className="w-full p-4 text-left focus:outline-none focus:ring-2 focus:ring-inset focus:ring-teal-600/40">
      <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={finding.dimension.replaceAll("_", " ")} tone="neutral" /><span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">{finding.segment_type}</span></div><StatusBadge status={finding.status} /></div>
      <p className="mt-3 rounded-lg border border-slate-200/80 bg-slate-50 p-3 text-sm leading-6 text-slate-800 dark:border-slate-800 dark:bg-slate-950/50 dark:text-slate-200">{finding.span_text || "Exact text span was not captured for this finding."}</p>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500"><span>Offset {finding.span_start ?? "—"}–{finding.span_end ?? "—"}</span><span>{confidenceLabel(finding.confidence, finding.confidence_reliability)}</span><span>Evidence {finding.evidence_node_id}</span></div>
    </button>
  </article>;
}

function HighlightedDocumentText({ content, findings, selectedFindingId, onSelect }: { content: string; findings: ReportHighlight[]; selectedFindingId: string; onSelect: (id: string) => void }) {
  const characters = Array.from(content);
  const ranges = findings
    .filter((finding) => finding.span_start != null && finding.span_end != null && finding.span_end > finding.span_start)
    .sort((left, right) => (left.span_start || 0) - (right.span_start || 0));
  if (!ranges.length) return <p className="whitespace-pre-wrap text-sm leading-8 text-slate-700 dark:text-slate-300">{content}</p>;

  const parts: ReactNode[] = [];
  let cursor = 0;
  ranges.forEach((finding, index) => {
    const rawStart = finding.span_start as number;
    const rawEnd = finding.span_end as number;
    const start = Math.max(cursor, Math.min(rawStart, characters.length));
    const end = Math.min(Math.max(start, rawEnd), characters.length);
    if (start > cursor) parts.push(<span key={`text-${index}`}>{characters.slice(cursor, start).join("")}</span>);
    if (end <= start) return;
    const selected = finding.evidence_node_id === selectedFindingId;
    parts.push(<button key={finding.evidence_node_id} type="button" onClick={() => onSelect(finding.evidence_node_id)} aria-label={`Inspect finding: ${finding.title}`} className={cn("rounded px-0.5 text-left underline decoration-2 underline-offset-4 transition focus:outline-none focus:ring-2 focus:ring-teal-600/50", selected ? "bg-teal-200/80 text-teal-950 decoration-teal-700 dark:bg-teal-800/70 dark:text-teal-50 dark:decoration-teal-200" : finding.status === "EXPERIMENTAL" ? "bg-amber-100/80 decoration-amber-500 dark:bg-amber-950/50 dark:decoration-amber-400" : "bg-slate-200/80 decoration-slate-400 dark:bg-slate-800 dark:decoration-slate-500")}>{characters.slice(start, end).join("")}</button>);
    cursor = end;
  });
  if (cursor < characters.length) parts.push(<span key="text-tail">{characters.slice(cursor).join("")}</span>);
  return <p className="whitespace-pre-wrap text-sm leading-8 text-slate-700 dark:text-slate-300">{parts}</p>;
}

export default function DocumentEvidencePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const requestedVersion = useSearchParams().get("version") || "";
  const { currentOrg } = useStore();
  const [versionId, setVersionId] = useState("");
  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [documentContent, setDocumentContent] = useState<DocumentContent | null>(null);
  const [report, setReport] = useState<EvidenceFirstReport | null>(null);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [explainability, setExplainability] = useState<DetectionExplainability | null>(null);
  const [matches, setMatches] = useState<SimilarityMatch[]>([]);
  const [citationAnalysis, setCitationAnalysis] = useState<CitationAnalysis | null>(null);
  const [authorshipSignal, setAuthorshipSignal] = useState<AuthorshipSignal | null>(null);
  const [provenanceTimeline, setProvenanceTimeline] = useState<ProvenanceTimeline | null>(null);
  const [evidenceGraph, setEvidenceGraph] = useState<EvidenceGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [showHighConfidenceOnly, setShowHighConfidenceOnly] = useState(true);
  const [signalFamily, setSignalFamily] = useState("ALL");
  const [selectedFindingId, setSelectedFindingId] = useState("");

  useEffect(() => {
    if (!params.id || !currentOrg) return;
    let active = true;
    void (async () => {
      setLoading(true); setError(null);
      try {
        const [documentRecord, provenance] = await Promise.all([api.getDocument(params.id), api.getProvenanceTimeline(params.id)]);
        const version = requestedVersion || provenance.versions.at(-1)?.id;
        if (!version || !provenance.versions.some((item) => item.id === version)) throw new Error("Document version not found");
        const [content, similarity, citations, authorship, evidenceFirstReport, detectionResult, detectionExplanation] = await Promise.all([
          api.getDocumentContent(params.id, version).catch(() => null),
          api.getSimilarityMatches(params.id, version).catch(() => ({ matches: [] })),
          api.getCitationAnalysis(params.id, version),
          api.getAuthorshipAnalysis(params.id, version).catch(() => null),
          api.getEvidenceFirstReport(params.id, version).catch(() => null),
          api.getDetectionResult(params.id, version).catch(() => null),
          api.getDetectionExplain(params.id).catch(() => null),
        ]);
        if (!active) return;
        setDocument(documentRecord); setVersionId(version); setDocumentContent(content);
        setMatches(similarity.matches); setCitationAnalysis(citations); setAuthorshipSignal(authorship);
        setProvenanceTimeline(provenance); setEvidenceGraph(evidenceFirstReport?.graph || null);
        setReport(evidenceFirstReport); setDetection(detectionResult); setExplainability(detectionExplanation);
        setSelectedFindingId(evidenceFirstReport?.highlights[0]?.evidence_node_id || "");
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Unable to load version evidence"); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [params.id, currentOrg, requestedVersion]);

  const selectedVersion = provenanceTimeline?.versions.find((version) => version.id === versionId);
  const findings = useMemo(() => report?.highlights || [], [report]);
  const signalFamilies = useMemo(() => Array.from(new Set(findings.map((finding) => finding.dimension))).sort(), [findings]);
  const visibleFindings = useMemo(() => findings.filter((finding) => {
    const matchesFamily = signalFamily === "ALL" || finding.dimension === signalFamily;
    const matchesConfidence = !showHighConfidenceOnly || (finding.confidence != null && finding.confidence >= HIGH_CONFIDENCE_THRESHOLD);
    return matchesFamily && matchesConfidence;
  }), [findings, showHighConfidenceOnly, signalFamily]);
  const selectedFinding = visibleFindings.find((finding) => finding.evidence_node_id === selectedFindingId) || visibleFindings[0] || null;
  const selectedLimitations = report?.dimensions.find((dimension) => dimension.key === selectedFinding?.dimension)?.limitations || [];
  const documentLevelCount = findings.filter((finding) => finding.segment_type.toLowerCase() === "document").length;
  const paragraphLevelCount = findings.filter((finding) => finding.segment_type.toLowerCase() === "paragraph").length;
  const sentenceLevelCount = findings.filter((finding) => finding.segment_type.toLowerCase() === "sentence").length;

  const detectionState = detection ? stateLabels[detection.overall_verdict] || "INSUFFICIENT_EVIDENCE" : "INSUFFICIENT_EVIDENCE";
  const effectiveDetectionState = detection?.abstained && detectionState !== "UNCERTAIN" ? "INSUFFICIENT_EVIDENCE" : detectionState;
  const lastAnalyzed = report?.generated_at || detection?.created_at || document?.processed_at;
  const pipelineVersion = detection?.pipeline_version || "Not recorded";
  const modelVersion = detection?.model_version || "Not recorded";

  const focusFinding = (id: string) => {
    setSelectedFindingId(id);
    window.setTimeout(() => globalThis.document.getElementById(`finding-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  };

  const handleDownload = async () => {
    if (!params.id) return;
    setDownloading(true);
    setDownloadError("");
    try {
      const response = await api.getDocumentDownload(params.id, versionId);
      window.open(response.download_url, "_blank", "noopener,noreferrer");
    } catch (reason) {
      setDownloadError(reason instanceof Error ? reason.message : "Unable to prepare the document download.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <LoadingState label="Loading evidence workspace…" rows={8} />;
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;

  return <div className="max-w-[1600px]">
    <DegradedBanner />
    <PageHeader eyebrow="Review · evidence workspace" title={document?.title || document?.original_filename || "Document evidence"} description="Inspect the exact recorded spans, understand the statistical signal, and make a human decision without treating any signal as proof." action={<div className="flex flex-wrap gap-2"><Link href={`/reports?document=${params.id}&version=${versionId}`}><Button variant="secondary"><FileCheck2 size={16} aria-hidden="true" /> Full report</Button></Link><Link href={`/similarity?document=${params.id}&version=${report?.document_version_id || documentContent?.document_version_id || ""}`}><Button variant="secondary">Review similarity</Button></Link><Link href={`/write?document=${params.id}&version=${versionId}`}><Button variant="secondary">Improve with Write</Button></Link><Button variant="secondary" onClick={() => void handleDownload()} disabled={downloading}><Download size={16} aria-hidden="true" /> {downloading ? "Preparing…" : "Download"}</Button></div>} />
    <ModuleNav documentId={params.id} versionId={versionId} />
    <label className="mb-5 block text-sm font-semibold">Document version<select aria-label="Document analysis version" value={versionId} onChange={(event) => router.replace(`/documents/${params.id}?version=${event.target.value}`, { scroll: false })} className="ml-3 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900">{provenanceTimeline?.versions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number}</option>)}</select></label>

    <Panel className="mb-5" eyebrow="Analysis context" title="Version-scoped result" description="Every interpretation below belongs to this document version and its recorded pipeline metadata.">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Document status</p><div className="mt-2"><StatusBadge status={document?.status || "UNKNOWN"} /></div></div>
        <div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Analysis state</p><div className={cn("mt-2 inline-flex rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em]", stateClass(effectiveDetectionState))}>{effectiveDetectionState}</div></div>
        <div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Analysis version</p><p className="mt-2 break-all font-mono text-xs text-slate-700 dark:text-slate-300">{pipelineVersion}</p><p className="mt-1 text-[11px] text-slate-500">Model {modelVersion}</p></div>
        <div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Last analyzed</p><p className="mt-2 text-xs text-slate-700 dark:text-slate-300">{formatDate(lastAnalyzed)}</p><p className="mt-1 text-[11px] text-slate-500">Version {report?.document_version_id || detection?.document_version_id || "not recorded"}</p></div>
        <div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Confidence state</p><p className="mt-2 text-xs text-slate-700 dark:text-slate-300">{detection?.abstained ? "Abstained; review required" : confidenceLabel(detection?.confidence, detection?.confidence_reliability)}</p><p className="mt-1 text-[11px] text-slate-500">{detection?.release_status || report?.report_status || "Not tested"}</p></div>
      </div>
    </Panel>

    <div className="mb-5 grid overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_18px_55px_-38px_rgba(15,23,42,0.38)] dark:border-slate-800 dark:bg-slate-900 lg:grid-cols-[250px_minmax(0,1fr)_380px]">
      <aside className="border-b border-slate-200 p-5 dark:border-slate-800 lg:border-b-0 lg:border-r" aria-label="Document context">
        <div className="flex items-center gap-2 text-teal-800 dark:text-teal-300"><FileText size={17} aria-hidden="true" /><span className="text-[10px] font-bold uppercase tracking-[0.16em]">Document</span></div>
        <h2 className="mt-4 break-words text-base font-semibold text-slate-950 dark:text-white">{document?.title || document?.original_filename || "Untitled document"}</h2>
        <p className="mt-1 break-all text-xs text-slate-500">{document?.original_filename}</p>
        <dl className="mt-6 space-y-4 text-xs"><div><dt className="font-bold uppercase tracking-[0.12em] text-slate-600">Format</dt><dd className="mt-1 text-slate-700 dark:text-slate-300">{document?.extension?.toUpperCase() || document?.mime_type || "Not recorded"} · {formatBytes(document?.file_size)}</dd></div><div><dt className="font-bold uppercase tracking-[0.12em] text-slate-600">Words</dt><dd className="mt-1 text-slate-700 dark:text-slate-300">{documentContent ? documentContent.content.split(/\s+/).filter(Boolean).length : "Not recorded"}</dd></div><div><dt className="font-bold uppercase tracking-[0.12em] text-slate-600">Language</dt><dd className="mt-1 text-slate-700 dark:text-slate-300">{document?.language || "Not recorded"}</dd></div><div><dt className="font-bold uppercase tracking-[0.12em] text-slate-600">Fingerprint</dt><dd className="mt-1 break-all font-mono text-[10px] text-slate-500">{selectedVersion?.sha256_fingerprint || "Not recorded"}</dd></div></dl>
        <div className="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Recorded span coverage</p><div className="mt-3 grid grid-cols-3 gap-2 text-center"><div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950/60"><p className="text-lg font-semibold text-slate-900 dark:text-white">{sentenceLevelCount}</p><p className="text-[10px] text-slate-500">Sentences</p></div><div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950/60"><p className="text-lg font-semibold text-slate-900 dark:text-white">{paragraphLevelCount}</p><p className="text-[10px] text-slate-500">Paragraphs</p></div><div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-950/60"><p className="text-lg font-semibold text-slate-900 dark:text-white">{documentLevelCount}</p><p className="text-[10px] text-slate-500">Document</p></div></div></div>
        {downloadError && <p role="alert" className="mt-4 text-xs text-rose-700 dark:text-rose-300">{downloadError}</p>}
      </aside>

      <section className="min-w-0 border-b border-slate-200 dark:border-slate-800 lg:border-b-0 lg:border-r" aria-label="Highlighted text">
        <div className="border-b border-slate-100 p-5 dark:border-slate-800"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2 text-teal-800 dark:text-teal-300"><SlidersHorizontal size={16} aria-hidden="true" /><span className="text-[10px] font-bold uppercase tracking-[0.16em]">Evidence text</span></div><h2 className="mt-2 text-base font-semibold text-slate-950 dark:text-white">Recorded findings</h2><p className="mt-1 text-sm leading-6 text-slate-500">Only exact spans emitted by the analysis are shown. Missing spans are not reconstructed.</p></div><span className="text-xs text-slate-500">{visibleFindings.length} of {findings.length} visible</span></div><div className="mt-4 flex flex-wrap items-center gap-3"><label className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300"><input type="checkbox" checked={showHighConfidenceOnly} onChange={(event) => setShowHighConfidenceOnly(event.target.checked)} className="h-4 w-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600" /> High-confidence only <span className="font-normal text-slate-500">(≥70% recorded)</span></label><label className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300">Signal family<select value={signalFamily} onChange={(event) => setSignalFamily(event.target.value)} className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 font-medium outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"><option value="ALL">All families</option>{signalFamilies.map((family) => <option key={family} value={family}>{family.replaceAll("_", " ")}</option>)}</select></label>{showHighConfidenceOnly && <button type="button" onClick={() => setShowHighConfidenceOnly(false)} className="text-xs font-semibold text-teal-800 hover:underline dark:text-teal-300">Show all findings</button>}</div></div>
        <div className="max-h-[720px] overflow-y-auto bg-slate-50/50 p-5 dark:bg-slate-950/30">{documentContent ? <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"><div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800"><span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Normalized document text</span><span className="font-mono text-[10px] text-slate-500">{documentContent.pipeline_version} · v{documentContent.document_version_id.slice(0, 8)}</span></div><HighlightedDocumentText content={documentContent.content} findings={visibleFindings} selectedFindingId={selectedFinding?.evidence_node_id || ""} onSelect={setSelectedFindingId} /></div> : <div className="mb-4"><EmptyState icon={FileText} title="Document text unavailable" description="The authorized processed text was not available for this version. Recorded findings remain visible below; no text is reconstructed." /></div>}<div className="mt-5 flex items-center justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Finding list</p><h3 className="mt-1 text-base font-semibold text-slate-950 dark:text-white">Jump to a recorded span</h3></div><span className="text-xs text-slate-500">{visibleFindings.length} visible</span></div><div className="mt-3 space-y-3">{visibleFindings.length ? visibleFindings.map((finding) => <FindingCard key={finding.evidence_node_id} finding={finding} selected={finding.evidence_node_id === selectedFinding?.evidence_node_id} onSelect={() => setSelectedFindingId(finding.evidence_node_id)} />) : <EmptyState icon={FileText} title={findings.length ? "No findings match this view" : "No recorded text spans"} description={findings.length ? "Show all findings or change the signal family filter. The filter does not change the underlying analysis." : "The pipeline did not return an exact sentence, paragraph, or document span for this version."} action={findings.length ? <Button variant="secondary" onClick={() => { setShowHighConfidenceOnly(false); setSignalFamily("ALL"); }}>Show all findings</Button> : undefined} />}</div></div>
      </section>

      <aside className="min-w-0 bg-white dark:bg-slate-900" aria-label="Analysis and evidence panel">
        <div className="border-b border-slate-100 p-5 dark:border-slate-800"><Notice tone="warning"><strong>Interpret carefully.</strong> A writing signal describes statistical patterns. It does not prove misconduct, identify an author, or establish that an author used AI.</Notice></div>
        <div className="border-b border-slate-100 p-5 dark:border-slate-800"><div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Analysis conclusion</p><h2 className="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{effectiveDetectionState}</h2></div><span className={cn("rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em]", stateClass(effectiveDetectionState))}>{detection?.abstained ? "ABSTAINED" : detection?.release_status || "NOT TESTED"}</span></div><p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{detection?.abstention_reason || detection?.explanation || "No calibrated detection result is available for this document version. No classification is being inferred."}</p><p className="mt-3 text-xs text-slate-500">{detection?.abstained ? "Classification withheld because the evidence or calibration gate was insufficient." : confidenceLabel(detection?.confidence, detection?.confidence_reliability)}</p></div>
        <div className="p-5"><div className="mb-5 border-b border-slate-100 pb-5 dark:border-slate-800"><div className="flex items-center justify-between gap-3"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Finding navigator</p><span className="text-xs text-slate-500">{visibleFindings.length} visible</span></div><div className="mt-3 max-h-36 space-y-1 overflow-y-auto">{visibleFindings.slice(0, 20).map((finding) => <button key={finding.evidence_node_id} type="button" onClick={() => focusFinding(finding.evidence_node_id)} className={cn("flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs", selectedFinding?.evidence_node_id === finding.evidence_node_id ? "bg-teal-50 font-semibold text-teal-900 dark:bg-teal-950/40 dark:text-teal-200" : "text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800")}><span className="truncate">{finding.title}</span><span className="shrink-0 text-[10px] text-slate-600">{finding.segment_type}</span></button>)}{!visibleFindings.length && <p className="text-xs text-slate-500">No visible findings.</p>}</div></div>{selectedFinding ? <div><div className="flex items-center justify-between gap-3"><h2 className="text-base font-semibold text-slate-950 dark:text-white">Finding detail</h2><span className="text-xs text-slate-500">{visibleFindings.findIndex((finding) => finding.evidence_node_id === selectedFinding.evidence_node_id) + 1} / {visibleFindings.length}</span></div><dl className="mt-5 space-y-5 text-sm"><div><dt className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">What</dt><dd className="mt-1 font-semibold text-slate-900 dark:text-white">{selectedFinding.dimension.replaceAll("_", " ")} · {selectedFinding.status}</dd></div><div><dt className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Where</dt><dd className="mt-1 text-slate-700 dark:text-slate-300">{selectedFinding.segment_type} span {selectedFinding.span_start ?? "—"}–{selectedFinding.span_end ?? "—"}</dd></div><div><dt className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Why</dt><dd className="mt-1 leading-6 text-slate-700 dark:text-slate-300">{selectedFinding.explanation || "No explanation was recorded."}</dd></div><div><dt className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Evidence</dt><dd className="mt-1 space-y-1 text-slate-700 dark:text-slate-300"><p>Evidence ID: <span className="font-mono text-xs">{selectedFinding.evidence_node_id}</span></p>{selectedFinding.source_titles.length ? <p>Sources: {selectedFinding.source_titles.join(" · ")}</p> : <p>No source recorded for this finding.</p>}{(selectedFinding.claim_ids.length > 0 || selectedFinding.citation_ids.length > 0) && <p>{selectedFinding.claim_ids.length} claim(s) · {selectedFinding.citation_ids.length} citation(s)</p>}</dd></div><div><dt className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Confidence</dt><dd className="mt-1 text-slate-700 dark:text-slate-300">{confidenceLabel(selectedFinding.confidence, selectedFinding.confidence_reliability)}</dd></div><div><dt className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Limitation</dt><dd className="mt-1 leading-6 text-slate-700 dark:text-slate-300">{selectedLimitations.length ? <ul className="space-y-1">{selectedLimitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}</ul> : "No additional limitation was recorded for this finding."}</dd></div></dl><Link href={`/evidence-graph?document=${params.id}&version=${versionId}`} className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-teal-800 hover:underline dark:text-teal-300">Open canonical evidence graph <ArrowUpRight size={15} aria-hidden="true" /></Link></div> : <EmptyState icon={Info} title="Select a finding" description="Choose a recorded span to inspect its explanation, evidence, confidence, and limitations." />}</div>
      </aside>
    </div>

    <div className="grid gap-5 lg:grid-cols-2">
      <Panel eyebrow="Analysis explanation" title="What this analysis does and does not prove"><div className="space-y-3 text-sm leading-6 text-slate-600 dark:text-slate-300"><p>{explainability?.what_this_means || "This workspace presents versioned statistical signals and their recorded evidence."}</p><p>{explainability?.what_this_does_not_prove || "It does not prove authorship, misconduct, or AI use."}</p>{(explainability?.known_limitations || []).length > 0 && <details><summary className="cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-200">Known limitations ({explainability?.known_limitations.length})</summary><ul className="mt-2 space-y-1 text-xs text-slate-500">{explainability?.known_limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}</ul></details>}</div></Panel>
      <Panel eyebrow="Connected evidence" title="Continue your review" description="Each area remains linked to the same tenant-scoped document version."><div className="grid gap-2 sm:grid-cols-2"><Link href={`/reports?document=${params.id}&version=${versionId}`} className="rounded-xl border border-slate-200 p-3 text-sm font-semibold text-slate-800 hover:border-teal-300 hover:text-teal-900 dark:border-slate-800 dark:text-slate-200 dark:hover:text-teal-200">Analysis report <span className="block text-xs font-normal text-slate-500">{report?.dimensions.length || 0} dimensions</span></Link><Link href={`/evidence-graph?document=${params.id}&version=${versionId}`} className="rounded-xl border border-slate-200 p-3 text-sm font-semibold text-slate-800 hover:border-teal-300 hover:text-teal-900 dark:border-slate-800 dark:text-slate-200 dark:hover:text-teal-200">Evidence graph <span className="block text-xs font-normal text-slate-500">{evidenceGraph?.nodes.length || 0} nodes · {evidenceGraph?.edges.length || 0} edges</span></Link><Link href={`/citations?document=${params.id}&version=${versionId}`} className="rounded-xl border border-slate-200 p-3 text-sm font-semibold text-slate-800 hover:border-teal-300 hover:text-teal-900 dark:border-slate-800 dark:text-slate-200 dark:hover:text-teal-200">Citation integrity <span className="block text-xs font-normal text-slate-500">{citationAnalysis?.findings.length || 0} findings · {citationAnalysis?.sources.length || 0} sources</span></Link><Link href={`/authorship?document=${params.id}&version=${versionId}`} className="rounded-xl border border-slate-200 p-3 text-sm font-semibold text-slate-800 hover:border-teal-300 hover:text-teal-900 dark:border-slate-800 dark:text-slate-200 dark:hover:text-teal-200">Authorship consistency <span className="block text-xs font-normal text-slate-500">{authorshipSignal?.verdict || "Not tested"}</span></Link><Link href={`/provenance?document=${params.id}&version=${versionId}`} className="rounded-xl border border-slate-200 p-3 text-sm font-semibold text-slate-800 hover:border-teal-300 hover:text-teal-900 dark:border-slate-800 dark:text-slate-200 dark:hover:text-teal-200">Provenance <span className="block text-xs font-normal text-slate-500">{provenanceTimeline?.versions.length || 0} immutable versions</span></Link><div className="rounded-xl border border-slate-200 p-3 text-sm font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">Similarity <span className="block text-xs font-normal text-slate-500">{matches.length} verified matches · similarity is not plagiarism</span></div></div></Panel>
    </div>
  </div>;
}
