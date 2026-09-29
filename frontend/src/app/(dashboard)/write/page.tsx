"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, ApiError, type AegisRefineResult, type DocumentRecord, type ProvenanceTimeline } from "@/lib/api";
import { useStore } from "@/lib/store";
import { ErrorState, LoadingState, PageHeader, Panel } from "@/components/design-system";

const EDITORIAL_FOCUSES = [
  { id: "full", label: "All supported edits", description: "Review every available rule for grammar, phrasing, tone, and spacing.", editTypes: ["grammar", "clarity", "concision", "tone", "structure"] },
  { id: "correctness", label: "Grammar & spacing", description: "Find repeated words, punctuation, and spacing issues.", editTypes: ["grammar", "structure"] },
  { id: "clarity", label: "Clarity & brevity", description: "Find supported wordy phrases and padded openings.", editTypes: ["clarity", "concision"] },
  { id: "tone", label: "Academic tone", description: "Expand supported informal contractions while preserving your voice.", editTypes: ["tone"] },
] as const;
const button = "rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:text-slate-200";
const primary = `${button} border-transparent bg-indigo-700 text-white hover:bg-indigo-800 dark:text-white`;
type SaveOperation = { key: string; id: string };
type Draft = { base: string; text: string; updated: number; operation?: SaveOperation };

export default function WritePage({ mode = "editor" }: { mode?: "editor" | "humaniser" }) {
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
  const [focus, setFocus] = useState<(typeof EDITORIAL_FOCUSES)[number]["id"]>("full");
  const [selection, setSelection] = useState({ start: 0, end: 0 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [online, setOnline] = useState(true);
  const [title, setTitle] = useState("");
  const [history, setHistory] = useState<{ undo: string[]; redo: string[] }>({ undo: [], redo: [] });
  const generation = useRef(0);
  const autoSaveBlocked = useRef(false);
  const refineOperation = useRef<{ key: string; id: string } | null>(null);
  const operation = useRef<SaveOperation | null>(null);
  const dirty = text !== savedText;
  const latest = versions.at(-1);
  const selectedFocus = EDITORIAL_FOCUSES.find((item) => item.id === focus) || EDITORIAL_FOCUSES[0];
  const draftKey = useCallback((doc: string) => `verity:draft:v1:${user?.id}:${currentOrg?.id}:${doc}`, [user?.id, currentOrg?.id]);

  const loadVersion = useCallback(async (doc: string, chosen = "", recover = true, preserveHistory = false) => {
    const current = ++generation.current;
    setSelection({ start: 0, end: 0 });
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
      if (!preserveHistory) setHistory({ undo: [], redo: [] });
      autoSaveBlocked.current = false;
      setStatus(draft ? "Recovered draft from this tab" : "Saved version loaded");
      operation.current = draft?.operation && typeof draft.operation.key === "string" && typeof draft.operation.id === "string" ? draft.operation : null;
      return true;
    } catch (reason) {
      if (current === generation.current) setError(reason instanceof Error ? reason.message : "Unable to load this version");
      return false;
    } finally { if (current === generation.current) setBusy(""); }
  }, [draftKey]);

  useEffect(() => {
    if (!currentOrg || !user) return;
    let active = true;
    void (async () => {
      setLoading(true); setDocumentId(""); setText(""); setSavedText(""); setVersions([]); setVersionId("");
      try {
        const list = await api.getDocuments();
        const available = list.items.filter((item) => item.status !== "archived");
        const requestedRecord = requestedDocument ? await api.getDocument(requestedDocument) : available[0];
        const requested = requestedRecord?.status === "archived" ? available[0] : requestedRecord;
        if (!active) return;
        setDocuments(requested && !available.some((item) => item.id === requested.id) ? [requested, ...available] : available);
        setDocumentId(requested?.id || ""); setTitle(requested?.title || requested?.original_filename || "");
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

  const updateText = (value: string, recordHistory = true) => {
    if (busy || value === text) return;
    if (recordHistory) setHistory((current) => ({ undo: [...current.undo.slice(-99), text], redo: [] }));
    setSelection({ start: 0, end: 0 });
    generation.current += 1; setBusy(""); setText(value); setResult(null); setSelected([]); operation.current = null; autoSaveBlocked.current = false;
    try {
      sessionStorage.setItem(draftKey(documentId), JSON.stringify({ base: versionId, text: value, updated: Date.now() }));
      setStatus("Draft retained in this tab · autosave pending");
    } catch { setStatus("Browser recovery unavailable · keep this tab open or download your draft"); }
  };

  const undo = () => {
    const previous = history.undo.at(-1);
    if (busy || previous === undefined) return;
    setHistory({ undo: history.undo.slice(0, -1), redo: [...history.redo, text] });
    updateText(previous, false);
  };
  const redo = () => {
    const next = history.redo.at(-1);
    if (busy || next === undefined) return;
    setHistory({ undo: [...history.undo, text], redo: history.redo.slice(0, -1) });
    updateText(next, false);
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
    const key = JSON.stringify({ documentId, versionId, text, focus });
    if (refineOperation.current?.key !== key) refineOperation.current = { key, id: crypto.randomUUID() };
    setBusy("Reviewing"); setError("");
    try {
      const response = await api.refineDraft({ operation_id: refineOperation.current.id, document_id: documentId, document_version_id: versionId, text, preserve_voice: true, edit_types: [...selectedFocus.editTypes] });
      if (current !== generation.current) return;
      refineOperation.current = null;
      setResult(response); setSelected(response.changes.map((change) => change.id)); setStatus("Candidate ready for review");
    } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "Review failed; your draft is unchanged"); }
    finally { if (current === generation.current) setBusy(""); }
  };

  const improveSelection = async (editTypes: string[]) => {
    if (busy || selection.end <= selection.start) return;
    const current = generation.current;
    const key = JSON.stringify({ documentId, versionId, text, selection, editTypes });
    if (refineOperation.current?.key !== key) refineOperation.current = { key, id: crypto.randomUUID() };
    setBusy("Reviewing selection"); setError("");
    try {
      const changes = await api.suggestEdits({ operation_id: refineOperation.current.id, document_id: documentId, document_version_id: versionId, text, span_start: selection.start, span_end: selection.end, preserve_voice: true, edit_types: editTypes });
      if (current !== generation.current) return;
      refineOperation.current = null;
      setResult({ document_id: documentId, document_version_id: versionId, original_text: text, revised_text: text, changes, disclaimer: "Limited editorial rules applied only within your selection. Review each suggestion before saving." });
      setSelected(changes.map((change) => change.id)); setStatus("Selection ready for review");
    } catch (reason) { if (current === generation.current) setError(reason instanceof Error ? reason.message : "Selection review failed; your draft is unchanged"); }
    finally { if (current === generation.current) setBusy(""); }
  };

  const save = useCallback(async (accept: boolean, restore = false, automatic = false) => {
    const current = generation.current;
    const base = restore ? latest?.id : versionId;
    if (!base) return;
    const ids = accept ? [...selected].sort() : [];
    const key = JSON.stringify({ documentId, base, text, ids, restore, versionId });
    if (operation.current?.key !== key) operation.current = { key, id: crypto.randomUUID() };
    // Persist the exact operation before sending so a lost response followed by
    // reload reuses the server's idempotency identity, for ordinary draft saves.
    try { sessionStorage.setItem(draftKey(documentId), JSON.stringify({ base: versionId, text, updated: Date.now(), operation: operation.current })); } catch { /* Server idempotency still protects retries in this render. */ }
    setBusy("Saving"); setError("");
    try {
      const response = restore
        ? await api.restoreDocumentVersion(documentId, versionId, { operation_id: operation.current.id, base_version_id: base })
        : await api.saveEditorRevision(documentId, { operation_id: operation.current.id, base_version_id: base, text, edit_ids: ids });
      if (current !== generation.current) return;
      const loaded = await loadVersion(documentId, response.id, false, true);
      if (!loaded) { setStatus("Saved on server · reload to recover your draft"); return; }
      try { sessionStorage.removeItem(draftKey(documentId)); } catch { /* Saving is independent of browser storage. */ }
      autoSaveBlocked.current = false;
      setStatus(`${automatic ? "Autosaved" : "Saved"} version ${response.version_number}`);
    } catch (reason) {
      if (current !== generation.current) return;
      autoSaveBlocked.current = true;
      setStatus(reason instanceof ApiError && reason.status === 409 ? "Conflict · your draft is retained" : "Save failed · your draft is retained");
      setError(reason instanceof Error ? reason.message : "Unable to save; retry without changing your draft");
    } finally { if (current === generation.current) setBusy(""); }
  }, [documentId, draftKey, latest?.id, loadVersion, selected, text, versionId]);

  useEffect(() => {
    if (!dirty || !online || busy || !versionId || versionId !== latest?.id || !text.trim() || result || autoSaveBlocked.current) return;
    const timer = window.setTimeout(() => { void save(false, false, true); }, 1800);
    return () => window.clearTimeout(timer);
  }, [busy, dirty, latest?.id, online, result, save, text, versionId]);

  const rename = async () => {
    const current = documents.find((item) => item.id === documentId);
    if (!current || !title.trim()) return;
    setBusy("Renaming"); setError("");
    try {
      const updated = await api.renameDocument(documentId, title.trim(), current.title);
      setDocuments((items) => items.map((item) => item.id === updated.id ? updated : item));
      setTitle(updated.title || updated.original_filename); setStatus("Document renamed");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to rename document"); }
    finally { setBusy(""); }
  };

  const archive = async () => {
    if (dirty || !window.confirm("Archive this document? Its versions and evidence will be retained.")) return;
    setBusy("Archiving"); setError("");
    try {
      await api.deleteDocument(documentId);
      const remaining = documents.filter((item) => item.id !== documentId);
      setDocuments(remaining); setDocumentId(remaining[0]?.id || "");
      setTitle(remaining[0]?.title || remaining[0]?.original_filename || "");
      if (remaining[0]) await loadVersion(remaining[0].id);
      else { setVersions([]); setVersionId(""); setText(""); setSavedText(""); }
      setStatus("Document archived; historical evidence retained");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to archive document"); }
    finally { setBusy(""); }
  };

  const downloadDraft = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "verity-draft.txt"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  if (loading) return <LoadingState label="Loading document…" rows={4} />;
  return <div className="max-w-6xl"><PageHeader eyebrow={mode === "humaniser" ? "AI Humaniser" : "Document Editor"} title={mode === "humaniser" ? "Make your writing clearer" : "Edit your document"} description={mode === "humaniser" ? "Compare your original with suggested edits. Generative rewriting is unavailable until an approved private model is deployed; these are limited editorial rules." : "Work on a draft, review suggested edits, and save a new version without losing the original."} />
    {error && <div className="mb-5"><ErrorState message={error} /></div>}
    {!documents.length ? <Panel title="Start with a document"><Link href={`/check?next=${mode === "humaniser" ? "humaniser" : "editor"}`} className={primary}>Create or import a document</Link></Panel> : <>
      <Panel className="mb-5" title={mode === "humaniser" ? "Choose a document" : "Your document"} description="Each save appends a version. The original file remains available in history.">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Document<select disabled={!!busy} value={documentId} onChange={(event) => { const next = event.target.value; setDocumentId(next); setTitle(documents.find((item) => item.id === next)?.title || documents.find((item) => item.id === next)?.original_filename || ""); void loadVersion(next); }} className="mt-2 w-full min-w-0 rounded-lg border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-950">{documents.filter((item) => item.status !== "archived").map((item) => <option key={item.id} value={item.id}>{item.title || item.original_filename}</option>)}</select></label>
          <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Version history<select aria-label="Editor version history" disabled={!!busy} value={versionId} onChange={(event) => { if (!dirty || window.confirm("Keep the current draft in this tab and open another version? Editing that version will replace the retained draft.")) void loadVersion(documentId, event.target.value, false); }} className="mt-2 w-full min-w-0 rounded-lg border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-950">{versions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number} · {version.change_summary || version.edit_type}</option>)}</select></label>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2"><label className="min-w-52 flex-1 text-sm font-medium text-slate-700 dark:text-slate-200">Document title<input aria-label="Document title" maxLength={500} value={title} disabled={!!busy} onChange={(event) => setTitle(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-950" /></label><button className={button} disabled={!!busy || !online || !title.trim() || title.trim() === documents.find((item) => item.id === documentId)?.title} onClick={() => void rename()}>Rename</button><button className={button} disabled={!!busy || !online || dirty} onClick={() => void archive()}>Archive document</button></div>
        <label className="mt-4 block max-w-sm text-sm font-medium text-slate-700 dark:text-slate-200">Editorial focus
          <select disabled={!!busy} value={focus} onChange={(event) => { setFocus(event.target.value as typeof focus); setResult(null); setSelected([]); refineOperation.current = null; setStatus("Focus changed · review again for new suggestions"); }} className="mt-2 w-full rounded-lg border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-950">{EDITORIAL_FOCUSES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
        </label>
        <p className="mt-2 text-xs text-slate-500">{selectedFocus.description} Suggestions come from limited editorial rules, not a generative writing model.</p>
        <div className="mt-4 flex flex-wrap items-center gap-3"><Link href={`/documents/${documentId}`} className="text-sm font-semibold text-teal-800 hover:underline dark:text-teal-300">Advanced Analysis</Link><p role="status" aria-label="Editor status" className="text-sm text-slate-700 dark:text-slate-200">{!online ? "Offline · your draft remains in this tab" : busy || status}</p>{versionId && latest && versionId !== latest.id && <button className={button} disabled={!!busy || !online} onClick={() => void save(false, true)}>Restore this version</button>}<button className={button} disabled={!!busy} onClick={() => { if (!dirty || window.confirm("Keep the current draft in this tab and open the latest version? Editing it will replace the retained draft.")) void loadVersion(documentId, latest?.id || "", false); }}>Review latest version</button></div>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Your draft" description="Mechanical editing. Draft recovery lasts up to 24 hours in this tab and is cleared on sign-out.">
          <textarea aria-label="Draft text" value={text} readOnly={!!busy} onChange={(event) => updateText(event.target.value)} onSelect={(event) => { const input = event.currentTarget; setSelection({ start: Array.from(input.value.slice(0, input.selectionStart)).length, end: Array.from(input.value.slice(0, input.selectionEnd)).length }); }} onKeyDown={(event) => { if (busy || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return; event.preventDefault(); if (event.shiftKey) redo(); else undo(); }} className="min-h-80 w-full resize-y rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm leading-6 text-slate-900 focus:outline-2 focus:outline-indigo-600 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100" />
          {selection.end > selection.start && <div className="mt-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700" aria-label="Selection actions"><p className="mb-2 text-xs text-slate-600 dark:text-slate-300">Selected passage · limited editorial rules</p><div className="flex flex-wrap gap-2">{[{ label: "Improve selection", types: ["grammar", "clarity", "concision", "tone", "structure"] }, { label: "Shorten", types: ["concision"] }, { label: "Simplify", types: ["clarity"] }, { label: "Professionalise", types: ["tone"] }].map((action) => <button key={action.label} className={button} disabled={!!busy || !online || !versionId} onClick={() => void improveSelection(action.types)}>{action.label}</button>)}</div><p className="mt-2 text-xs text-slate-600 dark:text-slate-300">Humanise and Expand are unavailable until an approved private model is deployed.</p></div>}
          <div className="mt-3 text-xs text-slate-500">{text.trim() ? text.trim().split(/\s+/u).length : 0} words · {dirty ? "Unsaved changes" : "Saved version"}</div>
          <div className="mt-4 flex flex-wrap gap-2"><button className={primary} disabled={!!busy || !online || !versionId || !text.trim()} onClick={() => void refine()}>Improve draft</button><button className={button} disabled={!!busy || !online || !versionId || !dirty || !text.trim()} onClick={() => void save(false)}>Save draft</button><button className={button} disabled={!!busy || !history.undo.length} onClick={undo}>Undo</button><button className={button} disabled={!!busy || !history.redo.length} onClick={redo}>Redo</button><button className={button} disabled={!text} onClick={downloadDraft}>Download draft</button></div>
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
