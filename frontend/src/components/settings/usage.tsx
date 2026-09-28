"use client";

import { useEffect, useState } from "react";
import { api, type UsageSummary } from "@/lib/api";
import { Button, Notice } from "@/components/design-system";

const names: Record<string, string> = {
  document_upload: "Document uploads", document_processing: "Document processing",
  text_analyze: "Text analysis", text_verify: "Text verification",
  text_refine: "Generative refinement", editorial: "Editorial suggestions",
};

export function WorkspaceUsage() {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    api.getUsage().then((result) => { if (active) { setData(result); setError(""); } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load usage."); });
    return () => { active = false; };
  }, [refresh]);
  return <section aria-labelledby="usage-heading" className="mt-8 border-t border-slate-200 pt-6 dark:border-slate-800">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="usage-heading" className="text-base font-semibold">Workspace usage</h2><Button variant="secondary" onClick={() => setRefresh((value) => value + 1)}>Refresh usage</Button></div>
    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Monthly operation limits are shared across this workspace. Pending work reserves capacity; failed work releases it. Replaying the same operation does not use another unit. Billing is not enabled.</p>
    {error && <div role="alert" className="mt-3"><Notice tone="danger">{error}</Notice></div>}
    {!data && !error && <p role="status" className="mt-3 text-sm">Loading usage…</p>}
    {data && <><p className="mt-3 text-sm">UTC period: {data.period}</p><ul className="mt-3 grid gap-3 sm:grid-cols-2">{data.limits.map((item) => <li key={item.task} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><h3 className="text-sm font-semibold">{names[item.task] || item.task}</h3><p className="mt-1 text-sm">{item.committed} completed · {item.reserved} pending · {item.limit} limit</p></li>)}</ul><p className="mt-3 text-xs text-slate-500">A listed limit does not mean the feature is available. Private generative refinement requires an approved model.</p></>}
  </section>;
}
