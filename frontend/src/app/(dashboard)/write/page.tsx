"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, ApiError, type AegisRefineResult, type DocumentRecord, type ProvenanceTimeline } from "@/lib/api";
import { useStore } from "@/lib/store";
import { ErrorState, LoadingState, PageHeader, Panel } from "@/components/design-system";

const EDIT_TYPES = ["grammar", "clarity", "concision", "tone", "structure", "coherence"];
const button = "rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:text-slate-200";
const primary = `${button} border-transparent bg-indigo-700 text-white hover:bg-indigo-800 dark:text-white`;
type Draft = { base: string; text: string; updated: number };

export default function WritePage() {
  const { currentOrg, user } = useStore();
  const params = useSearchParams();
  const requestedDocument = params.get("document") || "";
  const requestedVersion = params.get("version") || "";
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [versions, setVersions] = useState<ProvenanceTimeline["versions"]>([]);
  const [versionId, setVersionId] = useState("");
  const [text, setText] = useState("");
  const [savedText, setSavedText] = useState("");
  const [result, setResult] = useState<AegisRefineResult | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [online, setOnline] = useState(true);
  const generation = useRef(0);
  const refineOperation = useRef<{ key: string; id: string } | null>(null);
  const operation = useRef<{ key: string; id: string } | null>(null);
  const dirty = text !== savedText;
  const latest = versions.at(-1);
  const draftKey = useCallback((doc: string) => `verity:draft:v1:${user?.id}:${currentOrg?.id}:${doc}`, [user?.id, currentOrg?.id]);

  const loadVersion = useCallback(async (doc: string, chosen = "", recover = true) => {
    const current = ++generation.current;
    setBusy("Loading version"); setError(""); setResult(null); setSelected([]); setVersionId("");
    try {
      const timeline = await api.getProvenanceTimeline(doc);
      let id = chosen || timeline.versions.at(-1)?.id;
      let draft: Draft | null = null;
      if (recover && !chosen) {
        try {
          const stored = sessionStorage.getItem(draftKey(doc));
          if (stored) {
            const parsed = JSON.parse(stored) as Draft;
            if (typeof parsed.text === "string" && typeof parsed.updated === "number" && Date.now() - parsed.updated < 86_400_000 && timeline.versions.some((version) => version.id === parsed.base)) {
              draft = parsed; id = parsed.base;
            } else sessionStorage.removeItem(draftKey(doc));
          }
        } catch { /* The editor remains usable when browser storage is disabled. */ }
      }
      if (!id) throw new Error("Document version not found");
      const content = await api.getDocumentContent(doc, id);
      if (current !== generation.current) return;
      setVersions(timeline.versions); setVersionId(id); setSavedText(content.content); setText(draft?.text ?? content.content);
      setStatus(draft ? "Recovered draft from this tab" : "Saved version loaded");
      operation.current = null;
    } catch (reason) {
      if (current === generation.current) setError(reason instanceof Error ? reason.message : "Unable to load this version");
    } finally { if (current === generation.current) setBusy(""); }
  }, [draftKey]);

  useEffect(() => {
    if (!currentOrg || !user) return;
    let active = true;
    void (async () => {
      setLoading(true); setDocumentId(""); setText(""); setSavedText(""); setVersions([]); setVersionId("");
      try {
        const list = await api.getDocuments();
        const requested = requestedDocument ? await api.getDocument(requestedDocument) : list.items[0];
        if (!active) return;
        setDocuments(requested && !list.items.some((item) => item.id === requested.id) ? [requested, ...list.items] : list.items);
        setDocumentId(requested?.id || "");
        if (requested) await loadVersion(requested.id, requestedVersion);
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : "Unable to load documents"); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; generation.current += 1; };
  }, [currentOrg, user, requestedDocument, requestedVersion, loadVersion]);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update(); window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const updateText = (value: string) => {
    generation.current += 1; setBusy(""); setText(value); setResult(null); setSelected([]); operation.current = null;
    try {
      sessionStorage.setItem(draftKey(documentId), JSON.stringify({ base: versionId, text: value, updated: Date.now() }));
      setStatus("Draft retained in this tab · not yet saved to the workspace");
    } catch { setStatus("Browser recovery unavailable · keep this tab open or download your draft"); }
  };

  const candidate = useMemo(() => {
    if (!result) return "";
    const characters = Array.from(result.original_text);
    const changes = result.changes.filter((change) => selected.includes(change.id)).sort((a, b) => b.span_start - a.span_start);
    for (const change of changes) characters.splice(change.span_start, change.span_end - change.span_start, ...Array.from(change.revision));
    return characters.join("");
  }, [result, selected]);

  const refine = async () => {
    const current = generation.current;
    const key = JSON.stringify({ documentId, versionId, text });
    if (refineOperation.current?.key !== key) refineOperation.current = { key, id: crypto.randomUUID() };
    setBusy("Reviewing"); setError("");
    try {
      const response = await api.refineDraft({ operation_id: refineOperation.current.id, document_id: documentId, document_version_id: versionId, text, preserve_voice: true, edit_types: EDIT_TYPES });
      if (current !== generation.current) return;
      refineOperation.current = null;
      setResult(response); setSelected(response.changes.map((change) => change.id)); setStatus("Candidate ready for review");
    } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "Review failed; your draft is unchanged"); }
    finally { if (current === generation.current) setBusy(""); }
  };

  const save = async (accept: boolean, restore = false) => {
    const current = generation.current;
    const base = restore ? latest?.id : versionId;
    if (!base) return;
    const ids = accept ? [...selected].sort() : [];
    const key = JSON.stringify({ documentId, base, text, ids, restore, versionId });
    if (operation.current?.key !== key) operation.current = { key, id: crypto.randomUUID() };
    setBusy("Saving"); setError("");
    try {
      const response = restore
        ? await api.restoreDocumentVersion(documentId, versionId, { operation_id: operation.current.id, base_version_id: base })
        : await api.saveEditorRevision(documentId, { operation_id: operation.current.id, base_version_id: base, text, edit_ids: ids });
      if (current !== generation.current) return;
      try { sessionStorage.removeItem(draftKey(documentId)); } catch { /* Saving is independent of browser storage. */ }
      await loadVersion(documentId, response.id, false);
      setStatus(`Saved version ${response.version_number}`);
    } catch (reason) {
      if (current !== generation.current) return;
      setStatus(reason instanceof ApiError && reason.status === 409 ? "Conflict · your draft is retained" : "Save failed · your draft is retained");
      setError(reason instanceof Error ? reason.message : "Unable to save; retry without changing your draft");
    } finally { if (current === generation.current) setBusy(""); }
  };

  const downloadDraft = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "verity-draft.txt"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  if (loading) return <LoadingState label="Loading AZAERON WRITE…" rows={4} />;
  return <div className="max-w-6xl"><PageHeader eyebrow="Verity Refine · responsible editing" title="Improve a draft without hiding its provenance" description="Review mechanical edits, save a new version, and retain the original." />
    {error && <div className="mb-5"><ErrorState message={error} /></div>}
    {!documents.length ? <Panel title="Start with a document"><Link href="/upload" className={primary}>Upload document</Link></Panel> : <>
      <Panel className="mb-5" title="Editorial session" description="Each save appends a version. Text revisions are saved as UTF-8 text; original files remain available in history.">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Document<select disabled={!!busy} value={documentId} onChange={(event) => { setDocumentId(event.target.value); void loadVersion(event.target.value); }} className="mt-2 w-full min-w-0 rounded-lg border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-950">{documents.map((item) => <option key={item.id} value={item.id}>{item.title || item.original_filename}</option>)}</select></label>
          <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Version history<select aria-label="Editor version history" disabled={!!busy} value={versionId} onChange={(event) => void loadVersion(documentId, event.target.value, false)} className="mt-2 w-full min-w-0 rounded-lg border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-950">{versions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number} · {version.change_summary || version.edit_type}</option>)}</select></label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3"><p role="status" aria-label="Editor status" className="text-sm text-slate-700 dark:text-slate-200">{!online ? "Offline · your draft remains in this tab" : busy || status}</p>{versionId && latest && versionId !== latest.id && <button className={button} disabled={!!busy || !online} onClick={() => void save(false, true)}>Restore this version</button>}<button className={button} disabled={!!busy} onClick={() => void loadVersion(documentId, latest?.id || "", false)}>Review latest version</button></div>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Your draft" description="Mechanical editing. Draft recovery lasts up to 24 hours in this tab and is cleared on sign-out.">
          <textarea aria-label="Draft text" value={text} readOnly={busy === "Saving" || busy === "Loading version"} onChange={(event) => updateText(event.target.value)} className="min-h-80 w-full resize-y rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm leading-6 text-slate-900 focus:outline-2 focus:outline-indigo-600 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100" />
          <div className="mt-4 flex flex-wrap gap-2"><button className={primary} disabled={!!busy || !online || !versionId || !text.trim()} onClick={() => void refine()}>Improve draft</button><button className={button} disabled={!!busy || !online || !versionId || !dirty || !text.trim()} onClick={() => void save(false)}>Save draft</button><button className={button} disabled={!!busy || !dirty} onClick={() => updateText(savedText)}>Undo draft edits</button><button className={button} disabled={!text} onClick={downloadDraft}>Download draft</button></div>
        </Panel>
        <Panel title="Reviewable editorial pass" description="The candidate remains separate until you accept it.">
          <div aria-label="Candidate text" className="min-h-80 whitespace-pre-wrap break-words rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm leading-6 text-slate-800 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-200">{result ? candidate : "Your revision will appear here after the editorial pass."}</div>
          {result && <><p className="mt-3 text-xs leading-5 text-slate-600 dark:text-slate-300">{result.disclaimer}</p><div className="mt-3 flex flex-wrap gap-2"><button className={primary} disabled={!!busy || !online || !selected.length} onClick={() => void save(true)}>Accept selected changes</button><button className={button} disabled={!!busy} onClick={() => { setResult(null); setSelected([]); setStatus("Candidate rejected · draft unchanged"); }}>Reject candidate</button></div></>}
        </Panel>
      </div>
      {result && <Panel className="mt-5" title="Original → revision → reason" description="Select only the suggestions you want to include in the next version.">
        {!result.changes.length ? <p className="text-sm text-slate-600 dark:text-slate-300">No supported mechanical changes were found.</p> : <div className="space-y-4">{result.changes.map((change, index) => <article key={change.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-700"><label className="flex items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-200"><input type="checkbox" checked={selected.includes(change.id)} disabled={!!busy} onChange={(event) => setSelected((items) => event.target.checked ? [...items, change.id] : items.filter((id) => id !== change.id))} />Include suggestion {index + 1}: {change.dimension.replaceAll("_", " ")}</label><div className="mt-3 grid gap-3 sm:grid-cols-2"><p className="break-words rounded bg-red-50 p-2 text-sm text-slate-800 dark:bg-red-950 dark:text-slate-100"><del>{change.original}</del></p><p className="break-words rounded bg-emerald-50 p-2 text-sm text-slate-800 dark:bg-emerald-950 dark:text-slate-100"><ins>{change.revision}</ins></p></div><p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{change.change_reason}</p></article>)}</div>}
      </Panel>}
    </>}
  </div>;
}
