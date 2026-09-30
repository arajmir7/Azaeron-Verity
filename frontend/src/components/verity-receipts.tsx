"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { type Receipt, agentButton } from "@/lib/agent";

export function ReceiptCard({ receipt, onDecision }: { receipt: Receipt; onDecision?: (receipt: Receipt) => void }) {
  const [record, setRecord] = useState(receipt);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const decide = async (decision: "ACCEPTED" | "REJECTED") => {
    setBusy(true); setError("");
    try {
      const result = await api.agent<Receipt>(`/receipts/${record.id}/decision`, { method: "POST", body: JSON.stringify({ decision, candidate_sha256: record.candidate_sha256 }) });
      setRecord(result); onDecision?.(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Decision was not saved. Review the latest document version and try again."); }
    finally { setBusy(false); }
  };
  return <article className="rounded-xl border border-slate-200 p-4 text-sm dark:border-slate-700">
    <p className="font-semibold">Verity Receipt · {record.decision}</p>
    <p className="mt-2">Verification: {record.verification.outcome.replaceAll("_", " ")} · {record.verification.semantic_checked ? "Independent semantic check recorded" : "No semantic verification recorded"}</p>
    {record.verification.limitations?.map((value) => <p key={value} className="mt-2 text-xs text-slate-600 dark:text-slate-300">{value}</p>)}
    <details className="mt-3"><summary className="cursor-pointer font-medium">Review candidate and evidence</summary>
      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 font-sans dark:bg-slate-950">{record.candidate_text}</pre>
      <details className="mt-3"><summary className="cursor-pointer">Candidate diff</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all text-xs">{record.candidate_diff || "No text change."}</pre></details>
      <dl className="mt-3 space-y-2 break-all text-xs"><div><dt>Source document / version</dt><dd>{record.document_id} / {record.source_version_id}</dd></div><div><dt>Input SHA256</dt><dd>{record.input_sha256}</dd></div><div><dt>Candidate SHA256</dt><dd>{record.candidate_sha256}</dd></div><div><dt>Policy revision</dt><dd>{record.policy_revision}</dd></div><div><dt>Result version / SHA256</dt><dd>{record.result_version_id || "No accepted version"} / {record.result_sha256 || "Not recorded"}</dd></div></dl>
      <details className="mt-3"><summary className="cursor-pointer">Model, tools and protected spans</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ model: record.model_evidence, tools: record.tool_calls, protected_spans: record.protected_spans, verification: record.verification, similarity_before: record.similarity_before, similarity_after: record.similarity_after }, null, 2)}</pre></details>
    </details>
    {record.decision === "PENDING" && <div className="mt-4 flex flex-wrap gap-2"><button className={agentButton} disabled={busy || !["VERIFIED", "ATTRIBUTION_REVIEW", "USER_REVIEW_REQUIRED"].includes(record.verification.outcome)} onClick={() => void decide("ACCEPTED")}>Approve this exact candidate</button><button className={agentButton} disabled={busy} onClick={() => void decide("REJECTED")}>Reject candidate</button></div>}
    {error && <p role="alert" className="mt-3 text-red-700 dark:text-red-300">{error}</p>}
    <p className="mt-3 text-xs text-slate-500">This receipt records actions and checks. It does not prove authorship or factual accuracy.</p>
  </article>;
}

export function DocumentReceipts({ documentId, revision, onAccepted }: { documentId: string; revision?: string; onAccepted?: () => void }) {
  const [items, setItems] = useState<Receipt[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.agent<{ items: Receipt[] }>(`/documents/${documentId}/receipts`).then((result) => { if (active) { setItems(result.items); setError(""); } }).catch(() => { if (active) setError("Receipts could not be loaded."); });
    return () => { active = false; };
  }, [documentId, revision]);
  return <details className="mt-4 rounded-xl border border-slate-200 p-4 dark:border-slate-700"><summary className="cursor-pointer text-sm font-semibold">Document History · Verity Receipts</summary><div className="mt-4 space-y-3">{error ? <p role="alert">{error}</p> : items.length ? items.map((receipt) => <ReceiptCard key={receipt.id} receipt={receipt} onDecision={(result) => { if (result.decision === "ACCEPTED") onAccepted?.(); }} />) : <p className="text-sm text-slate-500">No AI-assisted action receipts are recorded for you on this document.</p>}</div></details>;
}
