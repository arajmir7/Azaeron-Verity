"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ResolveMatch } from "@/components/resolve-match";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { FileText, Search } from "lucide-react";
import { api, type DocumentRecord, type ProvenanceTimeline, type SimilarityEvidence, type SimilarityWorkflow } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, EmptyState, ErrorState, LoadingState, ModuleNav, Notice, PageHeader, Panel, StatusBadge } from "@/components/design-system";

const names: Record<string, string> = {
  QUOTED: "Quoted", PARTIALLY_QUOTED: "Partially quoted", UNQUOTED: "Unquoted",
  CITATION_MARKER_PRESENT: "Citation marker nearby", NO_CITATION_DETECTED: "No citation detected",
  MISSING_QUOTATION_REVIEW: "Quotation needs review", MISSING_CITATION_REVIEW: "Citation needs review",
  QUOTED_TEXT: "Quoted words", CITATION_CONTEXT: "Cited sentences", BIBLIOGRAPHY: "Bibliography",
  SMALL_MATCH: "Below minimum match length", SOURCE_EXCLUDED: "Source excluded",
};
const label = (value: string) => names[value] || value.replaceAll("_", " ").toLowerCase();
const percent = (value: number | null) => value == null ? "Unavailable" : `${value.toFixed(2)}%`;

function Pager({ page, pageSize, total, noun, onPage }: { page: number; pageSize: number; total: number; noun: string; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
    <span>{total} {noun} · page {page} of {pages}</span>
    <div className="flex gap-2"><Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={`Previous ${noun} page`}>Previous</Button><Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={`Next ${noun} page`}>Next</Button></div>
  </div>;
}

function EvidencePane({ match, source }: { match: SimilarityEvidence; source?: boolean }) {
  return <section aria-label={source ? "Source evidence" : "Target evidence"} className="min-w-0 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-950">
    <h3 className="font-semibold">{source ? match.source_title : "Your document"}</h3>
    <p className="mb-4 mt-1 text-xs text-slate-500">Exact offsets {source ? `${match.source_span_start}–${match.source_span_end}` : `${match.document_span_start}–${match.document_span_end}`}</p>
    <p className="whitespace-pre-wrap break-words text-sm leading-7"><span className="text-slate-500">{source ? match.source_context_before : match.context_before}</span><mark className="bg-amber-100 text-slate-950">{source ? match.source_text : match.matched_text}</mark><span className="text-slate-500">{source ? match.source_context_after : match.context_after}</span></p>
    <p className="mt-4 break-all text-xs text-slate-500">Version {source ? match.source_document_version_id : match.document_version_id}</p>
  </section>;
}

export default function SimilarityPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryString = searchParams.toString();
  const documentId = searchParams.get("document") || "";
  const requestedVersion = searchParams.get("version") || "";
  const requestedMatch = searchParams.get("match") || "";
  const { currentOrg } = useStore();
  const [context, setContext] = useState<{ document: DocumentRecord; timeline: ProvenanceTimeline } | null>(null);
  const [report, setReport] = useState<SimilarityWorkflow | null>(null);
  const [detail, setDetail] = useState<SimilarityEvidence | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [linkCopied, setLinkCopied] = useState(false);
  const [pendingQuery, setPendingQuery] = useState<{ base: string; next: string } | null>(null);
  if (pendingQuery && pendingQuery.base !== queryString) setPendingQuery(null);
  // Reflect edits immediately while navigation and the evidence request settle.
  // A different URL (including browser history) always takes precedence.
  const controlQuery = pendingQuery?.base === queryString ? pendingQuery.next : queryString;
  const controls = new URLSearchParams(controlQuery);
  const excludedSourceIds = controls.getAll("excluded_source_version_ids");
  const versionId = requestedVersion || (context?.document.id === documentId ? context.timeline.versions.at(-1)?.id : "") || "";

  useEffect(() => {
    if (!currentOrg || !documentId) return;
    let active = true;
    void (async () => {
      setContext(null); setReport(null); setError("");
      try {
        const [document, timeline] = await Promise.all([api.getDocument(documentId), api.getProvenanceTimeline(documentId)]);
        if (active) setContext({ document, timeline });
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Unable to load document"); }
    })();
    return () => { active = false; };
  }, [currentOrg, documentId, refresh]);

  useEffect(() => {
    if (!currentOrg || !documentId || !versionId) return;
    let active = true;
    void (async () => {
      setBusy(true); setError(""); setDetail(null);
      const params = new URLSearchParams(queryString);
      params.delete("document"); params.delete("version"); params.delete("match");
      params.set("document_version_id", versionId);
      try {
        const result = await api.getSimilarityWorkflow(documentId, params.toString());
        const selected = requestedMatch && !result.matches.items.some((item) => item.id === requestedMatch)
          ? await api.getSimilarityEvidence(documentId, requestedMatch, params.toString()) : null;
        if (active) { setReport(result); setDetail(selected); }
      } catch (reason) { if (active) { setReport(null); setError(reason instanceof Error ? reason.message : "Unable to load similarity evidence"); } }
      finally { if (active) setBusy(false); }
    })();
    return () => { active = false; };
  }, [currentOrg, documentId, versionId, requestedMatch, queryString, refresh]);

  function update(values: Record<string, string | string[] | null>, reset = true) {
    const params = new URLSearchParams(controlQuery);
    params.set("version", versionId);
    if (reset) { params.set("page", "1"); params.set("source_page", "1"); }
    for (const [key, value] of Object.entries(values)) {
      params.delete(key);
      if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
      else if (value !== null) params.set(key, value);
    }
    setLinkCopied(false);
    setPendingQuery({ base: queryString, next: params.toString() });
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  async function run() {
    setBusy(true); setError("");
    try { await api.runSimilarity(documentId, versionId); setRefresh((value) => value + 1); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to run similarity"); }
    finally { setBusy(false); }
  }

  async function copyLink() {
    const params = new URLSearchParams(queryString); params.set("version", versionId);
    try { await navigator.clipboard.writeText(`${window.location.origin}${pathname}?${params}`); setLinkCopied(true); }
    catch { setError("Copy the current address to share this view with an authorized workspace member."); }
  }

  const selected = report?.matches.items.find((item) => item.id === requestedMatch) || detail || report?.matches.items[0];
  if (!documentId) return <EmptyState icon={FileText} title="Choose a document to review similarity" description="Open a document from your workspace, then select Review similarity." action={<Link href="/documents"><Button>Open documents</Button></Link>} />;
  const exclusions = report?.exclusions;

  return <div className="mx-auto max-w-7xl">
    <PageHeader eyebrow="Plagiarism Checker" title="Review matching text" description={context?.document.title || context?.document.original_filename || "Compare with indexed workspace sources. A match alone does not establish plagiarism."} action={<Button variant="secondary" onClick={() => void copyLink()} disabled={!report}>{linkCopied ? "Review link copied" : "Copy review link"}</Button>} />
    <ModuleNav documentId={documentId} versionId={versionId} />
    {context && <div className="mb-5 flex flex-wrap items-center gap-4"><label className="text-sm font-semibold">Document version<select aria-label="Similarity document version" value={versionId} onChange={(event) => { setReport(null); update({ version: event.target.value, match: null, group: null, source_version_id: null, excluded_source_version_ids: null }); }} className="ml-3 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900">{context.timeline.versions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number}</option>)}</select></label><span className="text-xs text-slate-500">{report?.analyzed_at ? `Analyzed ${new Date(report.analyzed_at).toLocaleString()}` : "No completed similarity snapshot"}</span></div>}
    {error && <div className="mb-5"><ErrorState message={error} onRetry={() => setRefresh((value) => value + 1)} /></div>}
    {busy && <p role="status" className="mb-3 text-sm text-teal-700">Loading similarity evidence…</p>}
    {!report && !error && <LoadingState label="Opening version-scoped similarity…" rows={3} />}
    {report && <div aria-busy={busy} className={busy ? "pointer-events-none opacity-60" : ""}>
      <Notice><strong>How to interpret this result. </strong>{report.interpretation}</Notice>
      {report.analysis_state === "NOT_ANALYZED" ? <Panel className="mt-5" title="Similarity has not been run for this version" description="Create a reproducible snapshot against the indexed sources currently available in this workspace."><Button onClick={() => void run()} disabled={busy}><Search size={16} /> Analyze similarity</Button></Panel> : <>
        <div className="my-5 grid gap-4 lg:grid-cols-[1fr_2fr]">
          <Panel title="Overall similarity" action={<StatusBadge status={report.analysis_state === "BOUNDED" ? "BOUNDED SEARCH" : "LEXICAL EVIDENCE"} tone="neutral" />}>
            <p data-testid="similarity-percentage" className="text-4xl font-semibold tracking-tight text-teal-900 dark:text-teal-200">{percent(report.summary.percentage)}</p>
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{report.summary.matched_words} unique matched words / {report.summary.eligible_words} eligible words</p>
            <p className="mt-2 text-xs text-slate-500">{report.summary.excluded_words} excluded words · {report.summary.included_match_count} included matches</p>
            {report.summary.percentage == null && <p className="mt-3 text-sm text-amber-800 dark:text-amber-200">{report.corpus[0].indexed_versions ? "No eligible words remain under these exclusions." : "No indexed comparison source was available. This is not a 0% similarity result."}</p>}
            {report.analysis_state === "BOUNDED" && <p className="mt-3 text-sm text-amber-800 dark:text-amber-200">Search limits were reached. This percentage is a lower bound from the recorded evidence.</p>}
          </Panel>
          <Panel title="Source categories" description="Coverage is limited to the sources this workspace can actually compare."><div className="grid gap-3 sm:grid-cols-3">{report.corpus.map((corpus) => <div key={corpus.category} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-950"><p className="text-sm font-semibold">{corpus.label}</p><p className="mt-2 break-words text-xs font-semibold text-teal-800 dark:text-teal-300">{corpus.state}</p><p className="mt-2 text-xs leading-5 text-slate-500">{corpus.indexed_versions != null ? `${corpus.indexed_versions} indexed comparison versions at analysis time` : corpus.note}</p></div>)}</div></Panel>
        </div>
        <Panel className="mb-5" title="Match groups" description="Groups describe observed citation and quotation markers. Their overlapping coverage is not additive.">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{report.groups.map((group) => <button key={group.key} aria-pressed={searchParams.get("group") === group.key} onClick={() => update({ group: group.key, match: null })} className={`rounded-xl border p-4 text-left ${searchParams.get("group") === group.key ? "border-teal-600 bg-teal-50 dark:bg-teal-950" : "border-slate-200 dark:border-slate-700"}`}><p className="text-sm font-semibold">{group.label}</p><p className="mt-3 text-lg font-semibold">{group.matches} matches</p><p className="mt-1 text-xs text-slate-500">{group.matched_words} unique words · {percent(group.percentage)}</p></button>)}</div>
          <div className="mt-4 flex flex-wrap gap-3"><Button variant="secondary" onClick={() => update({ group: null, source_version_id: null, match: null })}>All matches</Button>{report.flags.map((flag) => <span key={flag.code} className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">{label(flag.code)}: {flag.match_count} matches</span>)}</div>
        </Panel>
        <Panel className="mb-5" title="Exclusions" description="Changes recalculate coverage from the same recorded evidence. Excluded matches remain inspectable.">
          <fieldset className="flex flex-wrap items-center gap-x-6 gap-y-3" disabled={busy}>{([['exclude_quotes', 'Exclude quoted text'], ['exclude_cited', 'Exclude sentences with citation markers'], ['exclude_bibliography', 'Exclude bibliography']] as const).map(([key, text]) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" className="scroll-mt-28" checked={controls.has(key) ? controls.get(key) === "true" : key === "exclude_bibliography"} onChange={(event) => update({ [key]: String(event.target.checked) })} />{text}</label>)}<label className="flex items-center gap-2 text-sm">Minimum matching words<select aria-label="Minimum matching words" value={controls.get("min_match_words") || "5"} onChange={(event) => update({ min_match_words: event.target.value })} className="rounded border bg-transparent px-2 py-1">{[5, 8, 12, 20, 50, 100].map((value) => <option key={value}>{value}</option>)}</select></label></fieldset>
          <details className="mt-4 text-xs leading-6 text-slate-500"><summary className="cursor-pointer font-semibold">Calculation and reproducibility</summary><p className="mt-2">{report.calculation}</p><p className="mt-2 break-all">Exclusions fingerprint: {report.exclusions_hash}</p><pre className="mt-2 overflow-auto">{JSON.stringify(exclusions, null, 2)}</pre></details>
        </Panel>
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(240px,1fr)_minmax(0,2fr)]">
          <Panel title="Ranked top sources" description="Ranked by unique included target words per source version.">
            <div className="space-y-3">{report.sources.items.map((source) => <article key={source.source_document_version_id} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700"><button className="text-left text-sm font-semibold text-teal-900 hover:underline dark:text-teal-200" onClick={() => update({ source_version_id: source.source_document_version_id, match: null })}>{source.rank}. {source.title}</button><p className="mt-2 text-xs text-slate-500">{source.matched_words} unique words · {percent(source.percentage)} · {source.match_count} matches</p><p className="mt-1 text-xs text-slate-500">Private workspace document</p><label className="mt-3 flex items-center gap-2 text-xs"><input type="checkbox" className="scroll-mt-28" checked={excludedSourceIds.includes(source.source_document_version_id)} aria-label={`Exclude source ${source.title}`} onChange={(event) => { const ids = excludedSourceIds; update({ excluded_source_version_ids: event.target.checked ? [...ids, source.source_document_version_id] : ids.filter((id) => id !== source.source_document_version_id) }); }} />Exclude this source version</label></article>)}</div>
            {!report.sources.total && <p className="text-sm text-slate-500">No matching source evidence was recorded.</p>}
            <Pager page={report.sources.page} pageSize={report.sources.page_size} total={report.sources.total} noun="sources" onPage={(page) => update({ source_page: String(page) }, false)} />
          </Panel>
          <Panel title="Matched passages" description="Choose a passage to inspect target and source evidence side by side.">
            <label className="mb-3 flex items-center gap-2 text-xs"><input type="checkbox" className="scroll-mt-28" checked={controls.get("show_excluded") !== "false"} onChange={(event) => update({ show_excluded: String(event.target.checked), match: null })} />Show excluded matches</label>
            <div className="space-y-2">{report.matches.items.map((match) => <button key={match.id} aria-pressed={selected?.id === match.id} aria-label={`Inspect match ${match.id}`} onClick={() => update({ match: match.id }, false)} className={`block w-full rounded-xl border p-3 text-left ${selected?.id === match.id ? "border-teal-600 bg-teal-50 dark:bg-teal-950" : "border-slate-200 dark:border-slate-700"}`}><p className="line-clamp-2 text-sm">{match.matched_text}</p><p className="mt-2 text-xs text-slate-500">{match.source_title} · {label(match.quotation_status)} · {label(match.citation_status)}</p><p className="mt-1 text-xs text-slate-500">{match.included_words} included words · {match.excluded ? "Excluded" : "Included"}{match.exclusion_reasons.length ? ` · ${match.exclusion_reasons.map(label).join(", ")}` : ""}</p></button>)}</div>
            {!report.matches.total && <p className="py-5 text-sm text-slate-500">No matches in this view. Review the exclusions, source filter and available corpus before interpreting this result.</p>}
            <Pager page={report.matches.page} pageSize={report.matches.page_size} total={report.matches.total} noun="matches" onPage={(page) => update({ page: String(page), match: null }, false)} />
          </Panel>
        </div>
        {selected && <Panel className="mt-5" title="Side-by-side evidence" description="Highlights are the exact stored strings. Context is shown around each match; source versions are preserved.">
          <div className="mb-4 flex flex-wrap gap-2"><StatusBadge status={label(selected.quotation_status)} tone="neutral" /><StatusBadge status={label(selected.citation_status)} tone="neutral" /><StatusBadge status={selected.excluded ? "Excluded from summary" : "Included in summary"} tone="neutral" /></div>
          <div className="grid gap-4 md:grid-cols-2"><EvidencePane match={selected} /><EvidencePane match={selected} source /></div><ResolveMatch key={`${versionId}:${selected.id}`} documentId={documentId} versionId={versionId} matchId={selected.id} sourceTitle={selected.source_title} onAccepted={(id) => { update({ version: id, match: null }); setRefresh((value) => value + 1); }} />
          {selected.flags.map((flag) => <p key={flag.code} className="mt-3 text-sm text-amber-900 dark:text-amber-200"><strong>{label(flag.code)}: </strong>{flag.explanation}</p>)}
          <details className="mt-5 text-xs leading-6 text-slate-500"><summary className="cursor-pointer font-semibold">Exact evidence trail</summary><dl className="mt-3 grid gap-2 break-all"><div><dt>Match ID</dt><dd>{selected.id}</dd></div><div><dt>Canonical evidence node</dt><dd>{selected.evidence_node_id || "Unavailable"}</dd></div><div><dt>Source content SHA-256</dt><dd>{selected.source_content_hash}</dd></div><div><dt>Source text SHA-256</dt><dd>{selected.source_text_hash}</dd></div><div><dt>Target content SHA-256</dt><dd>{selected.target_content_hash}</dd></div><div><dt>Target text SHA-256</dt><dd>{selected.target_text_hash}</dd></div><div><dt>Retrieved</dt><dd>{selected.retrieved_at}</dd></div><div><dt>Pipeline / analysis</dt><dd>{report.pipeline_version} / {report.analysis_id}</dd></div></dl></details>
        </Panel>}
      </>}
      <Panel className="mt-5" title="What this similarity review does and does not prove"><ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600 dark:text-slate-300">{report.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></Panel>
    </div>}
  </div>;
}
