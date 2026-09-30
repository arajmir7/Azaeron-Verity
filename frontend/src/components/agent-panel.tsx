"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, MessageSquare, Paperclip, Plus, Sparkles } from "lucide-react";
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

export function AgentPanel({ context, selection, compact = false, onAccepted, initialConversationId, onConversationChange }: { initialConversationId?: string; onConversationChange?: (id?: string) => void; context?: Attachment; selection?: [number, number]; compact?: boolean; onAccepted?: () => void }) {
  const { currentOrg, user } = useStore();
  const [history, setHistory] = useState<Array<{ id: string; title: string }>>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [modelCheck, setModelCheck] = useState<"loading" | "ready" | "error">("loading");
  const [approvedModelCount, setApprovedModelCount] = useState(0);
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
    void api.agent<{ items: Array<{ id: string; title: string }> }>(`/conversations?q=${encodeURIComponent(query)}`).then((list) => {
      if (alive) setHistory(list.items);
    }).catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : "Unable to load conversations"); });
    void api.getDocuments().then((docs) => {
      if (alive) setDocuments(docs.items.filter((doc) => doc.status === "completed"));
    }).catch(() => { if (alive) setError((current) => current || "Documents could not be loaded. You can still ask a question without an attachment."); });
    void api.getModels().then((result) => {
      if (alive) { setApprovedModelCount(result.models.length); setModelCheck("ready"); }
    }).catch(() => { if (alive) setModelCheck("error"); });
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
  const open = useCallback(async (id: string) => {
    const token = ++epoch.current; stream.current?.close(); setPartial(""); setError(""); setPrompt(""); setReplacement(undefined); setBusy(true);
    try { const result = await load(id, token); if (token !== epoch.current) return; onConversationChange?.(id); const run = result?.runs.find(isRunning); if (run) watch(id, run.id); }
    catch (reason) { if (token === epoch.current) setError(reason instanceof Error ? reason.message : "Conversation unavailable"); }
    finally { if (token === epoch.current) setBusy(false); }
  }, [load, watch, onConversationChange]);
  useEffect(() => {
    if (initialConversationId && activeId.current !== initialConversationId) void open(initialConversationId);
  }, [initialConversationId, open]);
  const submit = async (text = prompt, tool?: AgentTool, replaces = replacement) => {
    if (!text.trim() || busy || running) return;
    const token = epoch.current; setBusy(true); setError(""); setPartial("");
    try {
      let id = activeId.current;
      if (!id) {
        const created = await api.agent<{ id: string; title: string }>("/conversations", { method: "POST", body: JSON.stringify({ title: text.trim().slice(0, 80).replace(/[\r\n\t]/g, " ") }) });
        if (token !== epoch.current) return;
        id = created.id; activeId.current = id; onConversationChange?.(id); setHistory((current) => [created, ...current]);
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
      if (action === "delete") { stream.current?.close(); epoch.current++; activeId.current = null; setHistory((items) => items.filter((item) => item.id !== active.id)); setActive(null); setPartial(""); setStatus("Conversation deleted"); onConversationChange?.(); }
      else { setHistory((items) => items.map((item) => item.id === active.id ? { ...item, title: rename } : item)); await load(active.id); setReceiptRevision(`renamed:${Date.now()}`); setStatus("Conversation renamed"); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Change could not be saved"); }
    finally { setBusy(false); }
  };
  return <section aria-label="Azaeron AI conversation" className={`grid min-w-0 items-stretch gap-4 ${compact ? "" : "lg:grid-cols-[218px_minmax(0,1fr)]"}`}>
    <aside className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-3.5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-2 px-1"><MessageSquare size={15} className="text-teal-800 dark:text-teal-300" aria-hidden="true" /><h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-600 dark:text-slate-300">Your chats</h2></div>
      <button className={`${button} flex min-h-11 w-full items-center justify-center gap-2 border-teal-950 bg-teal-950 text-white hover:bg-teal-900`} disabled={busy} onClick={() => { onConversationChange?.(); epoch.current++; stream.current?.close(); activeId.current = null; setActive(null); setPartial(""); setPrompt(""); setError(""); setStatus(""); }}><Plus size={16} aria-hidden="true" />New chat</button>
      <label className="mt-5 block text-xs font-semibold text-slate-600 dark:text-slate-300">Search history<input aria-label="Search conversations" className={`${input} mt-2 min-h-10`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a conversation" /></label>
      <nav aria-label="Conversation history" className={`${compact ? "max-h-28" : "max-h-[min(48vh,440px)]"} mt-3 space-y-1 overflow-auto`}>
        {history.length ? history.map((item) => <button key={item.id} disabled={busy} aria-current={active?.id === item.id ? "page" : undefined} className={`flex min-h-10 w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] hover:bg-teal-50 dark:hover:bg-slate-800 ${active?.id === item.id ? "bg-teal-50 font-semibold text-teal-950 dark:bg-teal-950 dark:text-teal-100" : "text-slate-700 dark:text-slate-300"}`} onClick={() => void open(item.id)}><MessageSquare size={14} className="shrink-0 opacity-65" aria-hidden="true" /><span className="truncate">{item.title}</span></button>) : <p className="px-2 py-3 text-xs leading-5 text-slate-500">{query ? "No matching conversations." : "Your saved conversations will appear here."}</p>}
      </nav>
      {active && <details className="mt-3 border-t border-slate-100 pt-3 text-sm dark:border-slate-800"><summary className="cursor-pointer px-1 text-xs font-semibold text-slate-600 dark:text-slate-300">Conversation options</summary><label className="mt-3 block text-xs">Conversation name<input className={`${input} mt-1`} value={rename} maxLength={200} onChange={(event) => setRename(event.target.value)} /></label><div className="mt-2 flex flex-wrap gap-2"><button className={button} disabled={busy || !rename.trim()} onClick={() => void modify("rename")}>Rename</button><button className={button} disabled={busy || !!running} onClick={() => { if (window.confirm("Delete this conversation? Accepted versions and receipts remain in Document History.")) void modify("delete"); }}>Delete</button></div></details>}
      <p className="mt-auto hidden border-t border-slate-100 px-1 pt-4 text-[11px] leading-5 text-slate-500 dark:border-slate-800 dark:text-slate-400 lg:block">Private workspace history</p>
    </aside>
    <div className="flex h-[min(680px,calc(100vh-18rem))] min-h-[500px] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800 sm:px-6"><div className="min-w-0"><h2 className="truncate text-[15px] font-semibold text-slate-950 dark:text-white">{active?.title || "Azaeron AI"}</h2><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Private conversation · {target ? "Document context attached" : "No document attached"}</p></div><span className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-200"><span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true" />{modelCheck === "loading" ? "Checking model registry" : modelCheck === "error" ? "Model status unavailable" : approvedModelCount === 0 ? "Generation unavailable" : `${approvedModelCount} approved model${approvedModelCount === 1 ? "" : "s"}`}</span></header>
      <div role="log" aria-live="polite" tabIndex={0} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-600 sm:px-7 sm:py-6" aria-label="Conversation messages">
        {!active?.messages.length && !partial && <div className="my-auto w-full px-2 py-8 text-center"><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-teal-100 bg-teal-50 text-teal-800 dark:border-teal-900 dark:bg-teal-950 dark:text-teal-200"><Sparkles size={21} aria-hidden="true" /></span><h3 className="mt-5 font-serif text-[28px] tracking-[-0.035em] text-slate-950 dark:text-white">What would you like to work on?</h3><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500 dark:text-slate-400">Ask a question, explore a draft or bring a document into the conversation.</p><p className="mx-auto mt-5 max-w-lg text-xs leading-5 text-slate-500 dark:text-slate-400">Messages are saved in your workspace. AI generation starts only when an approved private model is available.</p></div>}
        {active?.messages.map((message) => <article key={message.id} className={`max-w-[min(88%,760px)] rounded-2xl px-4 py-3.5 ${message.role === "user" ? "ml-auto bg-[#edf4ef] dark:bg-teal-950/50" : "mr-auto border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"}`}><p className="mb-2 text-[11px] font-semibold text-slate-600 dark:text-slate-300">{message.role === "user" ? "You" : "Azaeron"}</p><p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-900 dark:text-slate-100">{message.content}</p><div className="mt-3 flex flex-wrap gap-2"><button className={button} onClick={() => { void navigator.clipboard.writeText(message.content).then(() => setStatus("Copied")).catch(() => setError("Copy failed. Select the text and copy it manually.")); }}>Copy</button>{message.role === "user" ? <><button className={button} disabled={busy || !!running} onClick={() => { setPrompt(message.content); setReplacement(message.id); composer.current?.focus(); }}>Edit prompt</button><button className={button} disabled={busy || !!running} onClick={() => { const run = active.runs.find((item) => item.message_id === message.id); const tool = active.tool_calls.find((item) => item.run_id === run?.id)?.arguments; void submit(message.content, tool, message.id); }}>Regenerate</button></> : <button className={button} disabled={busy || !!running || !target} onClick={() => { if (target) void submit("Prepare this reply as a document version for my review", { ...target, name: "document.create_version", message_id: message.id }); }}>Save to document</button>}</div></article>)}
        {partial && <div className="mr-auto max-w-[min(88%,760px)] whitespace-pre-wrap break-words rounded-2xl border border-teal-200 bg-white px-4 py-3.5 text-sm leading-7 dark:bg-slate-900"><p className="mb-2 text-[11px] text-slate-500">Draft response · verification in progress</p>{partial}</div>}
        {active?.tool_results.map((result) => <details key={result.id} className="max-w-[min(88%,760px)] rounded-xl border border-slate-200 p-3 dark:border-slate-700" open><summary className="cursor-pointer text-sm font-semibold">{active.tool_calls.find((call) => call.id === result.tool_call_id)?.name} · recorded result</summary><ToolEvidence content={result.content} /></details>)}
        {running && <p role="status" className="text-xs text-slate-500">{status || "Working…"}</p>}
      </div>
      {error && <p role="alert" className="mx-4 mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-100 sm:mx-6">{error}</p>}
      <footer className="border-t border-slate-200 bg-[#fbfcfa] px-3 py-3 dark:border-slate-800 dark:bg-slate-950/60 sm:px-5 sm:py-4"><div className="mx-auto max-w-4xl">
        <form className="rounded-2xl border border-slate-300 bg-white px-3.5 py-3 shadow-[0_8px_24px_-22px_rgba(15,23,42,.55)] focus-within:border-teal-600 dark:border-slate-700 dark:bg-slate-900" onSubmit={(event) => { event.preventDefault(); void submit(); }}><label className="sr-only" htmlFor="azaeron-prompt">{replacement ? "Edit prompt and send a new turn" : "Ask Azaeron AI"}</label><textarea id="azaeron-prompt" ref={composer} className="min-h-[68px] w-full resize-y border-0 bg-transparent px-1 py-1 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-500 focus:ring-0 dark:text-white dark:placeholder:text-slate-400" maxLength={8000} value={prompt} disabled={busy} onChange={(event) => setPrompt(event.target.value)} placeholder="Message Azaeron AI…" /><div className="mt-2 flex min-h-10 items-center justify-between gap-3"><p role="status" className="min-w-0 truncate text-[11px] text-slate-500 dark:text-slate-400">{status || (target ? `Attached · version ${target.document_version_id.slice(0, 8)}` : "Private workspace chat")}</p>{running ? <button type="button" className={`${button} border-slate-300`} onClick={() => { void api.agent(`/runs/${running.id}/cancel`, { method: "POST" }).then(() => { setStatus("Stopped"); setPartial(""); }).catch(() => setError("Stop could not be confirmed. The run may still be active.")); }}>Stop</button> : <button type="submit" aria-label="Send" className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal-950 text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-teal-700 dark:hover:bg-teal-600" disabled={busy || !prompt.trim()}><ArrowUp size={18} aria-hidden="true" /></button>}</div></form>
        <div className="mt-2.5 flex flex-wrap items-center gap-2.5">{!context && <details className="relative"><summary className="inline-flex min-h-9 cursor-pointer list-none items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"><Paperclip size={14} aria-hidden="true" />Add context</summary><div className="absolute bottom-11 left-0 z-20 max-h-[65vh] w-[min(34rem,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-900"><DocumentIntake onReady={(attachment) => { setAttachments([attachment]); setStatus("Document attached"); }} /><label className="block text-xs font-semibold">Existing document<select aria-label="Existing document" className={`${input} my-2 min-h-10`} value={attachments[0]?.document_id || ""} disabled={busy || !!running} onChange={(event) => void selectAttachment(event.target.value)}><option value="">Choose a document</option>{documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.title || doc.original_filename}</option>)}</select></label></div></details>}
          {target && <div className="flex max-w-full flex-wrap gap-1.5">{[{ name: "document.read", label: "Read" }, { name: "document.summarize", label: "Summarise" }, { name: "writing.refine", label: "Humanise", focus: "humanise" }, { name: "detection.analyze", label: "Check AI" }, { name: "similarity.analyze", label: "Compare" }].map((tool) => <button key={tool.label} type="button" className="min-h-9 rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 hover:border-teal-300 hover:text-teal-900 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" disabled={busy || !!running} onClick={() => shortcut(tool.name, tool.label, tool.focus)}>{tool.label}</button>)}</div>}
          {target && <details className="relative ml-auto"><summary className="min-h-9 cursor-pointer list-none rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium dark:border-slate-700 dark:bg-slate-900">Voice</summary><div className="absolute bottom-10 right-0 z-20 max-h-[60vh] w-[min(28rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-900"><VoiceProfiles key={`${currentOrg?.id}:${user?.id}`} sample={target} selected={voiceProfile} onSelect={setVoiceProfile} disabled={busy || !!running} /></div></details>}<p className="ml-auto hidden text-[10px] text-slate-500 xl:block">Responses require approved private models.</p></div>
      </div>{active && <details className="mx-auto mt-2 max-w-4xl px-5 text-xs"><summary className="cursor-pointer text-slate-500">Trust Drawer · recorded tools and model evidence</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-white p-3 text-[10px] dark:bg-slate-900">{JSON.stringify({ document_versions: active.attachments || attachments, executed_tools: active.tool_calls || [], models: active.runs.map((run) => ({ status: run.status, evidence: run.model_evidence })) || [], policy: "verity-agent-1" }, null, 2)}</pre></details>}{target && <DocumentReceipts key={target.document_id} documentId={target.document_id} revision={receiptRevision} onAccepted={onAccepted} />}</footer>
    </div>
  </section>;
}
