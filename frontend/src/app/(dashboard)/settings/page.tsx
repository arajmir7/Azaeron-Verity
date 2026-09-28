"use client";

import { useState } from "react";
import { ApiKeys } from "@/components/settings/api-keys";
import { WorkspaceUsage } from "@/components/settings/usage";
import { PrivacyControls } from "@/components/settings/privacy";
import { IdentitySecurity } from "@/components/settings/identity";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, LockKeyhole, ShieldCheck } from "lucide-react";
import { useStore, type Organization } from "@/lib/store";
import { selectWorkspace } from "@/lib/workspace";
import { Button, EmptyState, Notice, PageHeader, Panel, StatusBadge, WorkspaceSetup } from "@/components/design-system";

type SettingsTab = "profile" | "workspace" | "security";

export default function SettingsPage() {
  const { user, organizations, currentOrg } = useStore();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<SettingsTab>(requestedTab === "workspace" || requestedTab === "security" ? requestedTab : "profile");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [switching, setSwitching] = useState(false);

  const handleOrgSwitch = async (organization: Organization) => {
    setSwitching(true); setMessage(""); setError("");
    try { const selected = await selectWorkspace(organization); setMessage(`Workspace changed to ${selected.name}.`); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to switch workspace."); } finally { setSwitching(false); }
  };

  return <div><PageHeader eyebrow="Workspace preferences" title="Settings" description="Manage your profile, active workspace, and security posture." />{message && <div className="mb-5"><Notice tone="success"><span className="inline-flex items-center gap-2"><CheckCircle2 size={16} /> {message}</span></Notice></div>}{error && <div className="mb-5"><Notice tone="danger">{error}</Notice></div>}<Panel><div role="group" aria-label="Settings sections" className="flex flex-wrap gap-1 border-b border-slate-100 pb-3 dark:border-slate-800">{(["profile", "workspace", "security"] as SettingsTab[]).map((tab) => <button type="button" aria-pressed={activeTab === tab} key={tab} onClick={() => setActiveTab(tab)} className={`rounded-lg px-3 py-2 text-sm font-semibold capitalize transition ${activeTab === tab ? "bg-teal-50 text-teal-950 dark:bg-teal-950/50 dark:text-teal-200" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-white"}`}>{tab}</button>)}</div><div role="region" aria-label={`${activeTab} settings`} className="pt-6">{activeTab === "profile" && <div className="max-w-xl"><h2 className="text-base font-semibold text-slate-900 dark:text-white">Profile</h2><p className="mt-1 text-sm text-slate-500">Your identity for audit events and workspace access.</p><label className="mt-6 block text-sm font-semibold text-slate-700 dark:text-slate-200">Email<input aria-label="Email" type="email" value={user?.email || ""} disabled className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-100 px-3 py-2.5 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950" /></label><p className="mt-3 text-xs text-slate-500">Profile editing is not enabled by the current API.</p></div>}{activeTab === "workspace" && <div><h2 className="text-base font-semibold text-slate-900 dark:text-white">Your workspaces</h2><p className="mt-1 text-sm text-slate-500">Switching changes which documents and evidence are visible.</p>{organizations.length ? <div className="mt-5 grid gap-3 md:grid-cols-2">{organizations.map((organization) => <div key={organization.id} className={`rounded-xl border p-4 ${currentOrg?.id === organization.id ? "border-teal-300 bg-teal-50/60 dark:border-teal-800 dark:bg-teal-950/20" : "border-slate-200 dark:border-slate-800"}`}><div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-slate-900 dark:text-white">{organization.name}</p><p className="mt-1 text-xs text-slate-500">{organization.slug}</p></div>{currentOrg?.id === organization.id ? <StatusBadge status="ACTIVE" /> : <Button variant="secondary" onClick={() => void handleOrgSwitch(organization)} disabled={switching}>Switch</Button>}</div><p className="mt-4 inline-flex items-center gap-2 text-xs font-medium text-slate-500"><ShieldCheck size={14} /> Role: {organization.role || "not reported"}</p></div>)}</div> : <div className="mt-5"><EmptyState icon={LockKeyhole} title="No workspaces available" description="Create your first workspace below to begin." /></div>}<div className="mt-6"><WorkspaceSetup compact /></div>{currentOrg && <WorkspaceUsage key={currentOrg.id} />}</div>}{activeTab === "security" && <div className="max-w-xl"><IdentitySecurity key={user?.id} />{currentOrg && <ApiKeys key={currentOrg.id} organizationId={currentOrg.id} />}<PrivacyControls key={(user?.id || "") + (currentOrg?.id || "")} /></div>}</div></Panel></div>;
}
