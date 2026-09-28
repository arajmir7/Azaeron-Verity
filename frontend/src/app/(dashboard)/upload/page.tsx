"use client";

import { useCallback, useRef, useState } from "react";
import { CheckCircle2, FileText, FileUp, LockKeyhole, UploadCloud } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, DegradedBanner, EmptyState, Notice, PageHeader, Panel } from "@/components/design-system";

const ALLOWED_TYPES = [".pdf", ".docx", ".txt", ".md", ".html"];
const MAX_UPLOAD_SIZE = 100 * 1024 * 1024;
const MAX_PASTED_CHARACTERS = 200_000;

export default function UploadPage() {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const { currentOrg } = useStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState<"text" | "file">("text");
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const wordCount = draft.trim() ? draft.trim().split(/\s+/u).length : 0;

  const validateFile = useCallback((file: File) => {
    const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (!ALLOWED_TYPES.includes(extension)) return `File type not supported. Allowed: ${ALLOWED_TYPES.join(", ")}`;
    if (!file.size) return "The selected file is empty.";
    if (file.size > MAX_UPLOAD_SIZE) return "This file is larger than the 100 MB limit.";
    return null;
  }, []);

  const upload = useCallback(async (file: File, openDocument = false) => {
    setError(""); setUploading(true); setStatus("Requesting a secure upload slot…");
    try {
      if (!currentOrg) throw new Error("Select a workspace before uploading.");
      const request = await api.requestUpload(file.name, file.type || "application/octet-stream", file.size);
      setStatus("Uploading document…");
      const response = await fetch(request.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
      if (!response.ok) throw new Error("The storage upload failed. No document record was created.");
      setStatus("Computing SHA-256 fingerprint…");
      const buffer = await file.arrayBuffer();
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer))).map((byte) => byte.toString(16).padStart(2, "0")).join("");
      setStatus("Creating immutable document version…");
      const document = await api.confirmUpload(request.upload_id, request.storage_key, hash, file.name);
      setStatus("Queued for analysis.");
      const destinations: Record<string, string> = { detector: "/detector", plagiarism: "/plagiarism", humaniser: "/humaniser", editor: "/write" };
      const destination = next && destinations[next];
      router.push(destination ? `${destination}?document=${encodeURIComponent(document.id)}` : openDocument ? `/documents/${document.id}` : "/documents");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed."); setUploading(false);
    }
  }, [currentOrg, router, next]);

  const selectFile = (file?: File) => { if (!file) return; const validation = validateFile(file); if (validation) { setError(validation); return; } void upload(file); };
  const submitText = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle) { setError("Give your draft a title before creating the document."); return; }
    if (!draft.trim()) { setError("Paste or type some text before creating the document."); return; }
    const safeTitle = trimmedTitle.replace(/[\\/\x00-\x1f\x7f]/gu, " ").trim().slice(0, 100);
    if (!safeTitle) { setError("Use letters or numbers in the document title."); return; }
    const file = new File([draft], `${safeTitle}.txt`, { type: "text/plain" });
    const validation = validateFile(file);
    if (validation) { setError(validation); return; }
    void upload(file, true);
  };
  const handleInput = (event: React.ChangeEvent<HTMLInputElement>) => { selectFile(event.target.files?.[0]); event.target.value = ""; };
  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0]); };

  return <div>
    <DegradedBanner />
    <PageHeader eyebrow="Check · secure intake" title="Check a document" description="Paste a draft or upload a file. Either route creates a private, fingerprinted document version before analysis begins." />
    {!currentOrg ? <EmptyState icon={LockKeyhole} title="Workspace selection required" description="Select a workspace before creating a tenant-owned document." /> :
      <Panel title="Start with your work" description="The same versioned evidence workflow applies to pasted text and uploaded files.">
        <div>
          {error && <div className="mb-5" role="alert"><Notice tone="danger">{error}</Notice></div>}
          <div className="mb-5 flex flex-wrap gap-2" aria-label="Document input method">
            <button type="button" aria-pressed={mode === "text"} disabled={uploading} onClick={() => { setMode("text"); setError(""); }} className={`rounded-xl border px-4 py-2.5 text-sm font-semibold ${mode === "text" ? "border-teal-700 bg-teal-50 text-teal-950 dark:bg-teal-950 dark:text-teal-100" : "border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-300"}`}><FileText size={16} className="mr-2 inline" aria-hidden="true" />Paste or type</button>
            <button type="button" aria-pressed={mode === "file"} disabled={uploading} onClick={() => { setMode("file"); setError(""); }} className={`rounded-xl border px-4 py-2.5 text-sm font-semibold ${mode === "file" ? "border-teal-700 bg-teal-50 text-teal-950 dark:bg-teal-950 dark:text-teal-100" : "border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-300"}`}><UploadCloud size={16} className="mr-2 inline" aria-hidden="true" />Upload file</button>
          </div>
          <input ref={inputRef} aria-label="Document file" tabIndex={-1} className="sr-only" type="file" accept={ALLOWED_TYPES.join(",")} onChange={handleInput} />
          {uploading ? <div role="status" className="rounded-2xl border border-teal-200 bg-teal-50/70 px-6 py-12 text-center dark:border-teal-900/60 dark:bg-teal-950/20">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-teal-950 text-white"><FileUp size={21} aria-hidden="true" /></span>
            <p className="mt-4 text-base font-semibold text-teal-950 dark:text-teal-100">{status}</p>
            <p className="mt-2 text-xs text-teal-800 dark:text-teal-200">Keep this window open until the upload is confirmed.</p>
          </div> : mode === "text" ? <form onSubmit={submitText} className="space-y-4">
            <label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Document title
              <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={100} placeholder="e.g. Literature review draft" className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-normal outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 dark:border-slate-700 dark:bg-slate-950" />
            </label>
            <label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Your text
              <textarea value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={MAX_PASTED_CHARACTERS} placeholder="Paste or write a draft, then inspect its evidence and improve it in Write." className="mt-2 block min-h-72 w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 font-normal leading-7 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 dark:border-slate-700 dark:bg-slate-950" />
            </label>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-500">{wordCount.toLocaleString()} words · {draft.length.toLocaleString()} / {MAX_PASTED_CHARACTERS.toLocaleString()} characters</p>
              <Button type="submit" disabled={!title.trim() || !draft.trim()}><FileText size={16} aria-hidden="true" /> Create document</Button>
            </div>
            <p className="text-xs leading-5 text-slate-500">Your text is saved as a private TXT document. Review the analysis, citations and similarity against sources actually available to your workspace.</p>
          </form> : <div onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={handleDrop} className={`rounded-2xl border-2 border-dashed px-6 py-16 text-center transition-colors ${dragging ? "border-teal-600 bg-teal-50 dark:bg-teal-950/30" : "border-slate-300 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-950/30"}`}>
            <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-teal-800 shadow-sm dark:bg-slate-900 dark:text-teal-300"><UploadCloud size={25} aria-hidden="true" /></span>
            <h2 className="mt-5 text-lg font-semibold text-slate-900 dark:text-white">Drop a document here</h2>
            <p className="mt-2 text-sm text-slate-500">or choose a file from your device</p>
            <Button className="mt-6" onClick={() => inputRef.current?.click()}><UploadCloud size={16} aria-hidden="true" /> Choose document</Button>
            <p className="mt-5 text-xs text-slate-600 dark:text-slate-400">PDF, DOCX, TXT, Markdown or HTML · maximum 100 MB. Your original file is preserved.</p>
          </div>}
          <div className="mt-5 grid gap-3 text-xs text-slate-500 sm:grid-cols-3">
            <div className="flex gap-2"><CheckCircle2 size={15} className="text-emerald-600" /> Private workspace record</div>
            <div className="flex gap-2"><CheckCircle2 size={15} className="text-emerald-600" /> Content fingerprinted</div>
            <div className="flex gap-2"><CheckCircle2 size={15} className="text-emerald-600" /> Version-specific analysis</div>
          </div>
        </div>
      </Panel>}
  </div>;
}
