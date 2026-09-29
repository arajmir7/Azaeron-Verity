"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { type Conversation, type Receipt, agentButton, agentInput } from "@/lib/agent";
import { ReceiptCard } from "./verity-receipts";

export function ResolveMatch({ documentId, versionId, matchId, sourceTitle, onAccepted }: { documentId: string; versionId: string; matchId: string; sourceTitle: string; onAccepted: (version: string) => void }) {
  const [action, setAction] = useState("add_citation");
  const [citation, setCitation] = useState("");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const propose = async () => {
    setBusy(true); setError(""); setReceipt(null);
    try {
      const conv = await api.agent<{ id: string }>("/conversations", { method: "POST", body: JSON.stringify({ title: `Resolve match: ${sourceTitle}`.slice(0, 200) }) });
      const result = await api.agent<{ run: { id: string } }>(`/conversations/${conv.id}/messages`, { method: "POST", body: JSON.stringify({ operation_id: crypto.randomUUID(), content: "Prepare a source-attributed resolution for my review.", tool: { name: "similarity.resolve", document_id: documentId, document_version_id: versionId, match_id: matchId, action, citation, rationale } }) });
      for (let count = 0; count < 180 && alive.current; count++) {
        const current = await api.agent<Conversation>(`/conversations/${conv.id}`);
        const run = current.runs.find((item) => item.id === result.run.id);
        if (run && ["FAILED", "UNAVAILABLE", "CANCELLED"].includes(run.status)) throw new Error(run.status === "UNAVAILABLE" ? "Private rewriting is unavailable. Citation and quotation actions remain available." : "The resolution could not complete. Your document is unchanged.");
        if (run?.status === "COMPLETED") {
          const receiptId = current.tool_results.find((item) => item.content.receipt_id)?.content.receipt_id;
          const records = await api.agent<{ items: Receipt[] }>(`/documents/${documentId}/receipts`);
          const recorded = records.items.find((item) => item.id === receiptId);
          if (!recorded) throw new Error("The candidate receipt could not be loaded.");
          if (alive.current) setReceipt(recorded);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      if (alive.current) throw new Error("The run is still pending. Inspect it in Azaeron AI before starting another.");
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "Resolution failed"); }
    finally { if (alive.current) setBusy(false); }
  };
  return <details className="mt-5 rounded-xl border border-slate-200 p-4 dark:border-slate-700"><summary className="cursor-pointer text-sm font-semibold">Resolve match</summary><div className="mt-4 space-y-3">
    <p className="text-sm text-slate-600 dark:text-slate-300">Review attribution to {sourceTitle}. Each proposed change stays separate until you approve its exact candidate. Similarity runs again after approval.</p>
    <label className="block text-sm">Resolution<select className={`${agentInput} mt-1`} value={action} disabled={busy} onChange={(event) => setAction(event.target.value)}><option value="add_citation">Add citation</option><option value="quote_and_cite">Convert to quotation and cite</option><option value="paraphrase_with_attribution">Paraphrase with attribution · private model required</option><option value="remove_duplicate">Remove unnecessary duplicate</option><option value="keep_legitimate">Keep legitimate or common text</option></select></label>
    {!["remove_duplicate", "keep_legitimate"].includes(action) && <label className="block text-sm">Source citation<input className={`${agentInput} mt-1`} value={citation} disabled={busy} maxLength={2000} onChange={(event) => setCitation(event.target.value)} placeholder="Enter the accurate citation for this source" /></label>}
    <label className="block text-sm">Reason for this resolution<textarea className={`${agentInput} mt-1`} value={rationale} disabled={busy} maxLength={1000} onChange={(event) => setRationale(event.target.value)} /></label>
    <button className={agentButton} disabled={busy || !rationale.trim() || (!["remove_duplicate", "keep_legitimate"].includes(action) && !citation.trim())} onClick={() => void propose()}>Prepare resolution for review</button>
    {busy && <p role="status" className="text-sm">Preparing a reviewable candidate…</p>}{error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
    {receipt && <ReceiptCard receipt={receipt} onDecision={(result) => { if (result.result_version_id) onAccepted(result.result_version_id); }} />}
  </div></details>;
}
