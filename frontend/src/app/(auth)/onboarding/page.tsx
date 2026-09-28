"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { useStore, type ProductRole } from "@/lib/store";
import { loadWorkspaceSession, workspaceHome } from "@/lib/workspace";
import { AzaeronMark, Button, LoadingState, Notice } from "@/components/design-system";

const roles: Array<{ value: ProductRole; label: string; description: string }> = [
  { value: "student", label: "Student", description: "Check a paper and improve your draft." },
  { value: "teacher", label: "Teacher", description: "Review documents and inspect evidence." },
  { value: "professor", label: "Professor", description: "Review findings before a human decision." },
  { value: "researcher", label: "Researcher", description: "Inspect citations and source support." },
  { value: "reviewer", label: "Reviewer", description: "Follow findings to their evidence." },
  { value: "institution", label: "Institution", description: "Organize your document review work." },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { user, currentOrg } = useStore();
  const [ready, setReady] = useState(false);
  const [step, setStep] = useState<"role" | "invite">("role");
  const [role, setRole] = useState<ProductRole>("student");
  const [workspaceName, setWorkspaceName] = useState("");
  const [invitation, setInvitation] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api.getMe().then((profile) => {
      if (!active) return;
      useStore.getState().setUser(profile);
      if (profile.onboarding_completed) { router.replace(workspaceHome(profile)); return; }
      setRole(profile.product_role || "student");
      setReady(true);
    }).catch((reason) => {
      if (!active) return;
      if (reason?.status === 401) router.replace("/login");
      else { setError(reason instanceof Error ? reason.message : "Unable to load your account."); setReady(true); }
    });
    return () => { active = false; };
  }, [router]);

  const createPersonalWorkspace = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true); setError("");
    try {
      const profile = await api.completeOnboarding(role, workspaceName.trim() || undefined);
      await loadWorkspaceSession(profile);
      setStep("invite");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create your personal workspace. You can try again.");
    } finally { setSaving(false); }
  };

  const continueToWork = () => router.push(user?.home_path || "/check");
  const joinOrganization = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!invitation.trim()) { setError("Enter the invitation code shared by your workspace administrator."); return; }
    setSaving(true); setError("");
    try {
      await api.acceptInvitation(invitation.trim());
      const profile = await loadWorkspaceSession();
      router.push(workspaceHome(profile));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to accept this invitation. Your personal workspace is ready to use.");
    } finally { setSaving(false); }
  };

  return <main className="min-h-screen bg-[#f7faf8] px-5 py-10 text-slate-950 dark:bg-slate-950 dark:text-white">
    <div className="mx-auto max-w-2xl"><AzaeronMark /><div className="mt-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-10">
      <p className="text-xs font-bold uppercase tracking-widest text-teal-700 dark:text-teal-300">{step === "role" ? "1 of 2 · Your workspace" : "2 of 2 · Optional invitation"}</p>
      {!ready ? <LoadingState label="Loading your account…" /> : <>
        <h1 className="mt-3 font-serif text-4xl tracking-tight">{step === "role" ? "How will you use Azaeron?" : "Your personal workspace is ready."}</h1>
        <p className="mt-4 text-sm leading-6 text-slate-500">{step === "role" ? "Choose your starting workflow. We will create a free personal workspace for your documents. Your choice does not grant team permissions." : `${currentOrg?.name || "Your workspace"} is ready for your first document. You can also join a team using an invitation from its administrator.`}</p>
        {error && <div className="mt-5"><Notice tone="danger">{error}</Notice></div>}
        {step === "role" ? <form onSubmit={createPersonalWorkspace} className="mt-7 space-y-6">
          <fieldset><legend className="sr-only">Your role</legend><div className="grid gap-3 sm:grid-cols-2">{roles.map((item) => <label key={item.value} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${role === item.value ? "border-teal-600 bg-teal-50 dark:bg-teal-950/50" : "border-slate-200 dark:border-slate-700"}`}><input type="radio" name="product-role" value={item.value} checked={role === item.value} onChange={() => setRole(item.value)} className="mt-1 accent-teal-800" /><span><span className="block text-sm font-semibold">{item.label}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{item.description}</span></span></label>)}</div></fieldset>
          <label className="block text-sm font-semibold">Workspace name <span className="font-normal text-slate-500">(optional)</span><input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} maxLength={100} placeholder={`${user?.first_name || "My"}’s workspace`} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 font-normal dark:border-slate-700 dark:bg-slate-950" /></label>
          <Button type="submit" disabled={saving}>{saving ? "Creating your workspace…" : "Create my personal workspace"}<ArrowRight size={16} /></Button>
        </form> : <div className="mt-7 space-y-6">
          <div className="flex items-center gap-2 text-sm font-semibold text-teal-800 dark:text-teal-300"><CheckCircle2 size={18} /> Personal workspace created · Free plan</div>
          <form onSubmit={joinOrganization} className="space-y-4"><label className="block text-sm font-semibold">Organization invitation code<input value={invitation} onChange={(event) => setInvitation(event.target.value)} autoComplete="off" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 font-normal dark:border-slate-700 dark:bg-slate-950" /></label><Button variant="secondary" type="submit" disabled={saving || !invitation.trim()}>{saving ? "Joining workspace…" : "Join organization"}</Button></form>
          <div className="border-t border-slate-200 pt-6 dark:border-slate-700"><Button onClick={continueToWork} disabled={saving}>Continue to my first document<ArrowRight size={16} /></Button><p className="mt-3 text-xs text-slate-500">An organization invitation is optional.</p></div>
        </div>}
      </>}
    </div></div>
  </main>;
}
