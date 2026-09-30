"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { type Attachment, type AgentTool, type AgentRun, type Conversation, agentButton as button, agentInput as input, isRunning } from "@/lib/agent";
import { DocumentIntake } from "./document-intake";
import { DocumentReceipts } from "./verity-receipts";
import { VoiceProfiles } from "./voice-profiles";
import { ToolEvidence } from "./tool-evidence";

const failures: Record<string, string> = {
  blocked_by_external_infrastructure: "Approved self-hosted AI is unavailable. Your message is saved; no response was invented.",
  no_approved_model: "No approved private model is available for this task.",
  model_registry_invalid: "The private model registry is unavailable.",
  queue_unavailable: "The processing queue is unavailable. Try again when it recovers.",
  tool_request_rejected: "The tool could not use that document or request. Check its version and try again.",
  authorization_changed: "Access changed during this action. Reopen your workspace.",
};

export function AgentPanel({ context, selection, compact = false, onAccepted }: { context?: Attachment; selection?: [number, number]; compact?: boolean; onAccepted?: () => void }) {
  const { currentOrg, user } = useStore();
  const [history, setHistory] = useState<Array<{ id: string; title: string }>>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>(context ? [context] : []);
  const [prompt, setPrompt] = useState("");
  const [voiceProfile, setVoiceProfile] = useState("");
  const [replacement, setReplacement] = useState<string>();
  const [query, setQuery] = useState("");
  const [rename, setRename] = useState("");
  const [busy, setBusy] = useState(false);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [receiptRevision, setReceiptRevision] = useState("");
  const stream = useRef<EventSource | null>(null);
  const epoch = useRef(0);
  const retry = useRef<{ fingerprint: string; id: string } | null>(null);
  const activeId = useRef<string | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const running = active?.runs.find(isRunning);
  const target = context || attachments[0];
  const load = useCallback(async (id: string, token = epoch.current) => {
    const result = await api.agent<Conversation>(`/conversations/${id}`);
    if (token !== epoch.current) return;
    activeId.current = id; setActive(result); setRename(result.title);
    return result;
  }, []);
  useEffect(() => {
    let alive = true;
    void Promise.all([api.agent<{ items: Array<{ id: string; title: string }> }>(`/conversations?q=${encodeURIComponent(query)}`), api.getDocuments()]).then(([list, docs]) => {
      if (alive) { setHistory(list.items); setDocuments(docs.items.filter((doc) => doc.status === "completed")); }
    }).catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : "Unable to load conversations"); });
    return () => { alive = false; };
  }, [currentOrg?.id, user?.id, query, receiptRevision]);
  useEffect(() => () => { epoch.current++; stream.current?.close(); }, []);
  const watch = useCallback((conversationId: string, runId: string) => {
    stream.current?.close();
    const token = epoch.current;
    const source = new EventSource(`/api/v1/ai/conversations/${conversationId}/stream?run_id=${runId}`, { withCredentials: true });
    stream.current = source;
    let received = 0;
    const listen = (name: string, action: (value: Record<string, unknown>) => void) => source.addEventListener(name, (raw) => {
      const event = raw as MessageEvent;
      if (token !== epoch.current) return;
      const sequence = Number(event.lastEventId || 0);
      if (sequence && sequence <= received) return;
      if (sequence) received = sequence;
      try { action(JSON.parse(event.data)); } catch { setError("The response stream could not be read. Reopen the conversation to recover saved events."); source.close(); }
    });
    listen("started", () => setStatus("Working"));
    listen("tool", (event) => setStatus(`Running ${String(event.name)}`));
    listen("delta", (event) => setPartial((current) => current + String(event.text || "")));
    listen("message", () => { setPartial(""); void load(conversationId, token).catch(() => setError("Saved reply could not be loaded.")); });
    listen("done", (event) => {
      source.close(); setPartial(""); setStatus(String(event.status)); setReceiptRevision(`${runId}:${Date.now()}`);
      if (event.code && event.status !== "CANCELLED") setError(failures[String(event.code)] || `This action is ${String(event.status).toLowerCase()}. No document was changed.`);
      void load(conversationId, token).catch(() => setError("The saved result could not be loaded."));
    });
    listen("access_revoked", () => { source.close(); setActive(null); setPartial(""); setError("Access expired. Sign in again to reopen this conversation."); });
    source.onerror = () => { if (token === epoch.current && source.readyState !== EventSource.CLOSED) setStatus("Reconnecting to saved events…"); };
  }, [load]);
  const open = async (id: string) => {
    const token = ++epoch.current; stream.current?.close(); setPartial(""); setError(""); setPrompt(""); setReplacement(undefined); setBusy(true);
    try { const result = await load(id, token); const run = result?.runs.find(isRunning); if (run) watch(id, run.id); }
    catch (reason) { if (token === epoch.current) setError(reason instanceof Error ? reason.message : "Conversation unavailable"); }
    finally { if (token === epoch.current) setBusy(false); }
  };
  const submit = async (text = prompt, tool?: AgentTool, replaces = replacement) => {
    if (!text.trim() || busy || running) return;
    const token = epoch.current; setBusy(true); setError(""); setPartial("");
    try {
      let id = activeId.current;
      if (!id) {
        const created = await api.agent<{ id: string; title: string }>("/conversations", { method: "POST", body: JSON.stringify({ title: text.trim().slice(0, 80).replace(/[\r\n\t]/g, " ") }) });
        if (token !== epoch.current) return;
        id = created.id; activeId.current = id; setHistory((current) => [created, ...current]);
      }
      const payload = { content: text, attachments, tool, replaces_message_id: replaces };
      const fingerprint = JSON.stringify({ id, ...payload });
      if (retry.current?.fingerprint !== fingerprint) retry.current = { fingerprint, id: crypto.randomUUID() };
      const result = await api.agent<{ run: AgentRun }>(`/conversations/${id}/messages`, { method: "POST", body: JSON.stringify({ ...payload, operation_id: retry.current.id }) });
      if (token !== epoch.current) return;
      retry.current = null; setPrompt(""); setReplacement(undefined);
      await load(id, token); watch(id, result.run.id);
    } catch (reason) { if (token === epoch.current) setError(reason instanceof Error ? reason.message : "Message could not be sent. Retry keeps the same operation identity."); }
    finally { if (token === epoch.current) setBusy(false); }
  };
  const shortcut = (name: string, label: string, focus?: string) => {
    if (!target) { setError("Attach a saved document to use this action."); return; }
    void submit(label, { ...target, name, ...(focus ? { focus, ...(voiceProfile ? { voice_profile_id: voiceProfile } : {}), ...(selection && selection[1] > selection[0] ? { selection } : {}) } : {}) }, undefined);
  };
  const selectAttachment = async (id: string) => {
    if (!id) { setAttachments([]); return; }
    const token = epoch.current; setBusy(true); setError("");
    try { const content = await api.getDocumentContent(id); if (token === epoch.current) setAttachments([{ document_id: id, document_version_id: content.document_version_id }]); }
    catch (reason) { if (token === epoch.current) setError(reason instanceof Error ? reason.message : "Attachment unavailable"); }
    finally { if (token === epoch.current) setBusy(false); }
  };
  const modify = async (action: "rename" | "delete") => {
    if (!active) return;
    setBusy(true); setError("");
    try {
      await api.agent(`/conversations/${active.id}`, { method: action === "rename" ? "PATCH" : "DELETE", ...(action === "rename" ? { body: JSON.stringify({ title: rename }) } : {}) });
      if (action === "delete") { stream.current?.close(); epoch.current++; activeId.current = null; setHistory((items) => items.filter((item) => item.id !== active.id)); setActive(null); setPartial(""); setStatus("Conversation deleted"); }
      else { setHistory((items) => items.map((item) => item.id === active.id ? { ...item, title: rename } : item)); await load(active.id); setReceiptRevision(`renamed:${Date.now()}`); setStatus("Conversation renamed"); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Change could not be saved"); }
    finally { setBusy(false); }
  };
  return <section aria-label="Azaeron AI conversation" className={`grid min-w-0 gap-4 ${compact ? "" : "lg:grid-cols-[230px_minmax(0,1fr)]"}`}>
    <aside className="min-w-0 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
      <button className={button} disabled={busy} onClick={() => { epoch.current++; stream.current?.close(); activeId.current = null; setActive(null); setPartial(""); setPrompt(""); setError(""); setStatus(""); }}>New conversation</button>
      <label className="mt-4 block text-xs font-semibold">Search conversations<input className={`${input} mt-2`} value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <nav aria-label="Conversation history" className={`${compact ? "max-h-28" : "max-h-96"} mt-3 space-y-1 overflow-auto`}>{history.map((item) => <button key={item.id} disabled={busy} aria-current={active?.id === item.id ? "page" : undefined} className="block w-full truncate rounded-lg px-2 py-2 text-left text-sm hover:bg-teal-50 dark:hover:bg-slate-800" onClick={() => void open(item.id)}>{item.title}</button>)}</nav>
      {active && <details className="mt-4 text-sm"><summary className="cursor-pointer">Conversation options</summary><label className="mt-3 block">Conversation name<input className={`${input} mt-1`} value={rename} maxLength={200} onChange={(event) => setRename(event.target.value)} /></label><div className="mt-2 flex flex-wrap gap-2"><button className={button} disabled={busy || !rename.trim()} onClick={() => void modify("rename")}>Rename</button><button className={button} disabled={busy || !!running} onClick={() => { if (window.confirm("Delete this conversation? Accepted versions and receipts remain in Document History.")) void modify("delete"); }}>Delete</button></div></details>}
    </aside>
    <div className="flex min-h-[65vh] min-w-0 flex-col rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
      <header className="border-b border-slate-200 p-4 dark:border-slate-700"><h2 className="font-semibold">{active?.title || "Create → Verify → Prove"}</h2><p className="mt-2 text-xs leading-5 text-slate-500">Private conversation history is available. Generation requires an approved self-hosted model. Document actions show recorded evidence.</p></header>
      <div role="log" aria-live="polite" className="max-h-[60vh] flex-1 space-y-4 overflow-auto p-4" aria-label="Conversation messages">
        {!active?.messages.length && <p className="py-8 text-sm text-slate-500">Start with a question, or attach a document to inspect its evidence.</p>}
        {active?.messages.map((message) => <article key={message.id} className={`rounded-xl p-4 ${message.role === "user" ? "bg-teal-50 dark:bg-teal-950/40" : "border border-slate-200 dark:border-slate-700"}`}><p className="mb-2 text-xs font-semibold">{message.role === "user" ? "You" : "Azaeron AI"}</p><p className="whitespace-pre-wrap break-words text-sm leading-7">{message.content}</p><div className="mt-3 flex flex-wrap gap-2"><button className={button} onClick={() => { void navigator.clipboard.writeText(message.content).then(() => setStatus("Copied")).catch(() => setError("Copy failed. Select the text and copy it manually.")); }}>Copy</button>{message.role === "user" ? <><button className={button} disabled={busy || !!running} onClick={() => { setPrompt(message.content); setReplacement(message.id); composer.current?.focus(); }}>Edit prompt</button><button className={button} disabled={busy || !!running} onClick={() => { const run = active.runs.find((item) => item.message_id === message.id); const tool = active.tool_calls.find((item) => item.run_id === run?.id)?.arguments; void submit(message.content, tool, message.id); }}>Regenerate</button></> : <button className={button} disabled={busy || !!running || !target} onClick={() => { if (target) void submit("Prepare this reply as a document version for my review", { ...target, name: "document.create_version", message_id: message.id }); }}>Save to document</button>}</div></article>)}
        {partial && <div className="whitespace-pre-wrap break-words rounded-xl border border-teal-200 p-4 text-sm leading-7"><p className="mb-2 text-xs text-slate-500">Streaming draft · not yet verified</p>{partial}</div>}
        {active?.tool_results.map((result) => <details key={result.id} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700" open><summary className="cursor-pointer text-sm font-semibold">{active.tool_calls.find((call) => call.id === result.tool_call_id)?.name} · recorded result</summary><ToolEvidence content={result.content} /></details>)}
      </div>
      {error && <p role="alert" className="mx-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950 dark:text-amber-100">{error}</p>}
      <div className="border-t border-slate-200 p-4 dark:border-slate-700">
        {!context && <><DocumentIntake onReady={(attachment) => { setAttachments([attachment]); setStatus("Document attached"); }} /><label className="block text-xs font-semibold">Existing document<select className={`${input} my-2`} value={attachments[0]?.document_id || ""} disabled={busy || !!running} onChange={(event) => void selectAttachment(event.target.value)}><option value="">Choose a document</option>{documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.title || doc.original_filename}</option>)}</select></label></>}
        {target && <p className="mb-3 break-all text-xs text-slate-500">Attached version {target.document_version_id}{selection && selection[1] > selection[0] ? ` · selected characters ${selection[0]}–${selection[1]}` : ""}</p>}
        <div className="mb-3 flex flex-wrap gap-2">{[{ name: "document.read", label: "Read document" }, { name: "document.summarize", label: "Summarise" }, { name: "writing.refine", label: "Humanise", focus: "humanise" }, { name: "detection.analyze", label: "Check AI" }, { name: "similarity.analyze", label: "Check plagiarism" }, ...(compact ? [{ name: "writing.refine", label: "Improve", focus: "clarity" }, { name: "writing.refine", label: "Shorten", focus: "shorten" }, { name: "writing.refine", label: "Expand", focus: "expand" }, { name: "writing.refine", label: "Simplify", focus: "simplify" }] : [])].map((tool) => <button key={tool.label} className={button} disabled={busy || !!running || !target} onClick={() => shortcut(tool.name, tool.label, tool.focus)}>{tool.label}</button>)}</div>
        <VoiceProfiles key={`${currentOrg?.id}:${user?.id}`} sample={target} selected={voiceProfile} onSelect={setVoiceProfile} disabled={busy || !!running} />
        <form onSubmit={(event) => { event.preventDefault(); void submit(); }}><label className="block text-sm font-medium">{replacement ? "Edit prompt and send a new turn" : "Ask Azaeron AI"}<textarea ref={composer} className={`${input} mt-2 min-h-24 resize-y`} maxLength={8000} value={prompt} disabled={busy} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask about your writing or attached document…" /></label><div className="mt-3 flex items-center justify-between gap-3"><p role="status" className="text-xs text-slate-500">{status || "Your documents stay in this workspace."}</p>{running ? <button type="button" className={button} onClick={() => { void api.agent(`/runs/${running.id}/cancel`, { method: "POST" }).then(() => { setStatus("Stopped"); setPartial(""); }).catch(() => setError("Stop could not be confirmed. The run may still be active.")); }}>Stop</button> : <button type="submit" className={`${button} bg-teal-900 text-white hover:bg-teal-800`} disabled={busy || !prompt.trim()}>Send</button>}</div></form>
        <details className="mt-4 border-t border-slate-200 pt-3 text-sm dark:border-slate-700"><summary className="cursor-pointer font-semibold">Trust Drawer</summary><p className="mt-2 text-xs text-slate-500">Only executed tools and recorded model evidence appear here.</p><pre className="mt-3 max-h-60 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ document_versions: active?.attachments || attachments, executed_tools: active?.tool_calls || [], models: active?.runs.map((run) => ({ status: run.status, evidence: run.model_evidence })) || [], policy: "verity-agent-1" }, null, 2)}</pre></details>
        {target && <DocumentReceipts key={target.document_id} documentId={target.document_id} revision={receiptRevision} onAccepted={onAccepted} />}
      </div>
    </div>
  </section>;
}
