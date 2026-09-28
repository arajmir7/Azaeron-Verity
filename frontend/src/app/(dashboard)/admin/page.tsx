"use client";

import Link from "next/link";
import { LockKeyhole, Settings2, ShieldCheck } from "lucide-react";
import { useStore } from "@/lib/store";
import { EmptyState, PageHeader, Panel, StatusBadge } from "@/components/design-system";

export default function AdminPage() {
  const { currentOrg } = useStore();
  const allowed = ["owner", "admin"].includes((currentOrg?.role || "").toLowerCase());
  return <div><PageHeader eyebrow="Workspace administration" title="Admin" description="Access-controlled workspace configuration. Operational controls are shown only when the current role authorizes them." />{!currentOrg ? <EmptyState icon={LockKeyhole} title="Workspace selection required" description="Select a workspace before opening administration." /> : !allowed ? <div role="alert" className="rounded-2xl border border-amber-200 bg-amber-50 px-6 py-12 text-center dark:border-amber-900/60 dark:bg-amber-950/20"><LockKeyhole className="mx-auto text-amber-700 dark:text-amber-300" size={24} aria-hidden="true" /><h2 className="mt-4 text-base font-semibold text-amber-950 dark:text-amber-100">Permission denied</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-amber-900/80 dark:text-amber-200/80">Your role does not include workspace administration. Ask an owner or administrator for access.</p></div> : <div className="grid gap-5 lg:grid-cols-2"><Panel eyebrow="Current scope" title={currentOrg.name} action={<StatusBadge status={currentOrg.role || "authorized"} />}><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">You are authorized to manage this workspace. Changes remain subject to server-side authorization and audit logging.</p><Link href="/settings" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-teal-800 dark:text-teal-300"><Settings2 size={16} /> Open workspace settings</Link></Panel><Panel eyebrow="Integrity boundary" title="No fabricated administration metrics"><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">Usage, model, and compliance statistics are not displayed until the corresponding production APIs provide real, authorized records.</p><div className="mt-4 flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300"><ShieldCheck size={16} /> Server-authorized workspace</div></Panel></div>}</div>;
}
