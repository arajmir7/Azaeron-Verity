"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, type ErasureScope, type DocumentRecord } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, Notice } from "@/components/design-system";

const field = "mt-2 w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm";

export function PrivacyControls() {
  const { user, currentOrg } = useStore();
  const router = useRouter();
  const [scope, setScope] = useState<ErasureScope | "">("");
  const [documentId, setDocumentId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let active = true;
    if (scope === "document") api.getDocuments(page).then((result) => { if (active) { setDocuments(result.items); setTotal(result.total); setPageSize(result.page_size); } }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load documents."); });
    return () => { active = false; };
  }, [scope, page]);
  const target = scope === "account" ? user?.id : scope === "organization" ? currentOrg?.id : documentId;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!scope || !target || confirmation !== "ERASE") return;
    setBusy(true); setError("");
    try {
      const result = await api.requestErasure({ scope, target_id: target, current_password: password, mfa_code: mfaCode || undefined, confirmation: "ERASE" });
      if (!mounted.current) return;
      setPassword(""); setMfaCode("");
      if (!result.receipt) { setError("This erasure was already requested. Use the original receipt or contact your workspace administrator with the request ID: " + result.id); return; }
      // The fragment never enters server logs. Clear cached private drafts on
      // erasure and transfer the receipt only to the public status screen.
      const destination = "/erasure-status#" + new URLSearchParams({ id: result.id, receipt: result.receipt, clear_session: scope === "account" || scope === "organization" ? "1" : "0" }).toString();
      router.replace(destination);
      if (scope === "document") { try { for (const key of Object.keys(sessionStorage)) if (key.startsWith("verity:draft:v1:") && key.includes(target)) sessionStorage.removeItem(key); } catch { /* Storage may be unavailable. */ } }
    } catch (reason) { if (mounted.current) setError(reason instanceof Error ? reason.message : "Unable to request erasure."); }
    finally { if (mounted.current) { setBusy(false); setPassword(""); setMfaCode(""); } }
  }
  return <section aria-labelledby="privacy-heading" className="mt-8 border-t border-slate-200 pt-6 dark:border-slate-800">
    <h2 id="privacy-heading" className="text-base font-semibold">Privacy and data erasure</h2>
    <p id="erasure-policy" className="mt-2 text-sm text-slate-600 dark:text-slate-300">Erasure permanently removes the selected data, its versions, and analysis. It cannot be undone. Shared workspace content you do not own remains; account attribution is removed. Backups expire under the operator’s retention policy.</p>
    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Completion takes at least eight minutes while existing upload links expire and storage deletion is verified. A shared workspace’s sole owner must transfer ownership or erase the workspace before erasing their account.</p>
    {error && <div role="alert" className="mt-3"><Notice tone="danger">{error}</Notice></div>}
    <form onSubmit={submit} aria-describedby="erasure-policy" className="mt-4 space-y-4">
      <label className="block text-sm font-semibold">Data to erase<select required value={scope} onChange={(event) => { setScope(event.target.value as ErasureScope | ""); setConfirmation(""); setDocumentId(""); setPage(1); }} className={field}><option value="">Choose data</option>{currentOrg && <option value="document">A document and all its versions</option>}{currentOrg?.role?.toLowerCase() === "owner" && <option value="organization">Entire workspace: {currentOrg.name}</option>}<option value="account">My account and owned documents</option></select></label>
      {scope === "document" && <div><label className="block text-sm font-semibold">Document to erase<select required value={documentId} onChange={(event) => setDocumentId(event.target.value)} className={field}><option value="">Choose a document</option>{documents.map((document) => <option key={document.id} value={document.id}>{document.title || document.original_filename}</option>)}</select></label><div className="mt-2 flex flex-wrap items-center gap-2"><Button variant="secondary" type="button" disabled={busy || page <= 1} onClick={() => { setPage((value) => value - 1); setDocumentId(""); }}>Previous documents</Button><span className="text-xs">Page {page}</span><Button variant="secondary" type="button" disabled={busy || page * pageSize >= total} onClick={() => { setPage((value) => value + 1); setDocumentId(""); }}>Next documents</Button></div></div>}
      {scope && <><label className="block text-sm font-semibold">Password to authorize erasure<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className={field} /></label>{user?.mfa_enabled && <label className="block text-sm font-semibold">MFA code to authorize erasure<input autoComplete="one-time-code" required value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} className={field} /></label>}<label className="block text-sm font-semibold">Type ERASE to confirm<input autoComplete="off" required pattern="ERASE" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} className={field} /></label><Button type="submit" disabled={busy || !target || !password || confirmation !== "ERASE" || !!user?.mfa_enabled && !mfaCode}>{busy ? "Requesting erasure…" : "Permanently erase selected data"}</Button></>}
    </form>
  </section>;
}
