"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { type Attachment, agentButton, agentInput } from "@/lib/agent";

export function DocumentIntake({ onReady }: { onReady: (attachment: Attachment) => void }) {
  const [mode, setMode] = useState<"text" | "file">("text");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = async (file: File) => {
    if (!file.size || file.size > 10 * 1024 * 1024) { setError("Choose a nonempty file up to 10 MB."); return; }
    setBusy(true); setError(""); setStatus("Creating a private document…");
    try {
      const slot = await api.requestUpload(file.name, file.type || "application/octet-stream", file.size);
      const response = await fetch(slot.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
      if (!response.ok) throw new Error("Upload failed. Your text remains here.");
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map((value) => value.toString(16).padStart(2, "0")).join("");
      const document = await api.confirmUpload(slot.upload_id, slot.storage_key, digest, file.name);
      setStatus("Extracting text from the saved version…");
      // Processing remains a real worker operation. A timeout exposes its saved document.
      for (let count = 0; count < 45; count++) {
        const record = await api.getDocument(document.id);
        if (record.status === "failed") throw new Error("Document processing failed. Review the saved document in Documents.");
        if (record.status === "completed") {
          const content = await api.getDocumentContent(document.id);
          setStatus("Private version ready"); setDraft("");
          onReady({ document_id: document.id, document_version_id: content.document_version_id });
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Processing is still running. Choose the saved document when it is ready.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Intake failed. Your text remains here."); }
    finally { setBusy(false); }
  };
  return <details className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700"><summary className="cursor-pointer text-sm font-semibold">Paste, type or upload</summary><div className="mt-4 space-y-3">
    <div className="flex gap-2"><button className={agentButton} aria-pressed={mode === "text"} disabled={busy} onClick={() => setMode("text")}>Paste / type</button><button className={agentButton} aria-pressed={mode === "file"} disabled={busy} onClick={() => setMode("file")}>Upload</button></div>
    {mode === "text" ? <><label className="block text-sm">Text to analyse<textarea aria-label="Text to analyse" className={`${agentInput} mt-2 min-h-40`} maxLength={60000} disabled={busy} value={draft} onChange={(event) => setDraft(event.target.value)} /></label><button className={agentButton} disabled={busy || !draft.trim()} onClick={() => void upload(new File([draft], `Writing ${new Date().toISOString().slice(0, 10)}.txt`, { type: "text/plain" }))}>Use this text</button></> : <label className="block text-sm">Document file<input ref={fileInput} className="mt-2 block max-w-full text-sm" type="file" accept=".txt,.md,.pdf,.docx,.html" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = ""; }} /></label>}
    <p className="text-xs text-slate-500">This creates an immutable private document. Existing documents can be selected below.</p>
    {status && <p role="status" className="text-sm">{status}</p>}{error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
  </div></details>;
}
