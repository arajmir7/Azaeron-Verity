"use client";

import { useCallback, useRef, useState } from "react";
import { CheckCircle2, FileUp, LockKeyhole, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, DegradedBanner, EmptyState, Notice, PageHeader, Panel } from "@/components/design-system";

const ALLOWED_TYPES = [".pdf", ".docx", ".txt", ".md", ".html"];
const MAX_UPLOAD_SIZE = 100 * 1024 * 1024;

export default function UploadPage() {
  const router = useRouter();
  const { currentOrg } = useStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const validateFile = useCallback((file: File) => {
    const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (!ALLOWED_TYPES.includes(extension)) return `File type not supported. Allowed: ${ALLOWED_TYPES.join(", ")}`;
    if (!file.size) return "The selected file is empty.";
    if (file.size > MAX_UPLOAD_SIZE) return "This file is larger than the 100 MB limit.";
    return null;
  }, []);

  const upload = useCallback(async (file: File) => {
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
      await api.confirmUpload(request.upload_id, request.storage_key, hash, file.name);
      setStatus("Queued for analysis.");
      window.setTimeout(() => router.push("/documents"), 900);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed."); setUploading(false);
    }
  }, [currentOrg, router]);

  const selectFile = (file?: File) => { if (!file) return; const validation = validateFile(file); if (validation) { setError(validation); return; } void upload(file); };
  const handleInput = (event: React.ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0]);
  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0]); };

  return <div><DegradedBanner /><PageHeader eyebrow="Check · secure intake" title="Check a document" description="Start an evidence-first review. Your original file becomes an immutable version with a SHA-256 fingerprint before analysis begins." />{!currentOrg ? <EmptyState icon={LockKeyhole} title="Workspace selection required" description="Select a workspace before uploading a tenant-owned document." /> : <Panel title="Secure document intake" description="Accepted: PDF, DOCX, TXT, Markdown, and HTML · maximum 100 MB"><div aria-live="polite">{error && <div className="mb-5"><Notice tone="danger">{error}</Notice></div>}{uploading ? <div className="rounded-2xl border border-teal-200 bg-teal-50/70 px-6 py-12 text-center dark:border-teal-900/60 dark:bg-teal-950/20"><span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-teal-950 text-white"><FileUp size={21} aria-hidden="true" /></span><p className="mt-4 text-base font-semibold text-teal-950 dark:text-teal-100">{status}</p><p className="mt-2 text-xs text-teal-800 dark:text-teal-200">Keep this window open until the upload is confirmed.</p></div> : <div onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={handleDrop} className={`rounded-2xl border-2 border-dashed px-6 py-16 text-center transition-colors ${dragging ? "border-teal-600 bg-teal-50 dark:bg-teal-950/30" : "border-slate-300 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-950/30"}`}><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-teal-800 shadow-sm dark:bg-slate-900 dark:text-teal-300"><UploadCloud size={25} aria-hidden="true" /></span><h2 className="mt-5 text-lg font-semibold text-slate-900 dark:text-white">Drop a document here</h2><p className="mt-2 text-sm text-slate-500">or choose a file from your device</p><input ref={inputRef} aria-label="Document file" tabIndex={-1} className="sr-only" type="file" accept={ALLOWED_TYPES.join(",")} onChange={handleInput} /><Button className="mt-6" onClick={() => inputRef.current?.click()}><UploadCloud size={16} aria-hidden="true" /> Choose document</Button><p className="mt-5 text-xs text-slate-600 dark:text-slate-400">Your original file is preserved. Analysis results are version-specific.</p></div>}<div className="mt-5 grid gap-3 text-xs text-slate-500 sm:grid-cols-3"><div className="flex gap-2"><CheckCircle2 size={15} className="text-emerald-600" /> Server-authorized upload</div><div className="flex gap-2"><CheckCircle2 size={15} className="text-emerald-600" /> Content fingerprinted</div><div className="flex gap-2"><CheckCircle2 size={15} className="text-emerald-600" /> Processing is observable</div></div></div></Panel>}</div>;
}
