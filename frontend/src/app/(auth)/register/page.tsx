"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CheckCircle2, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { AzaeronMark, Button, Notice } from "@/components/design-system";
import { loadWorkspaceSession } from "@/lib/workspace";

export default function RegisterPage() {
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }
    if (password.length < 12) { setError("Password must be at least 12 characters."); return; }
    setLoading(true);
    try {
      await api.register(email.trim(), password, firstName.trim() || undefined, lastName.trim() || undefined);
      await api.login(email.trim(), password);
      await loadWorkspaceSession();
      router.push("/onboarding");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We could not create your account.");
    } finally {
      setLoading(false);
    }
  };

  return <main className="min-h-screen bg-[#f7faf8] text-slate-950 dark:bg-slate-950 dark:text-white"><div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(430px,0.78fr)]">
    <section className="relative hidden overflow-hidden bg-teal-950 p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-16"><div className="absolute inset-0 opacity-40" style={{ backgroundImage: "linear-gradient(rgba(204,240,216,.09) 1px, transparent 1px), linear-gradient(90deg, rgba(204,240,216,.09) 1px, transparent 1px)", backgroundSize: "54px 54px" }} /><div className="relative"><AzaeronMark /><div className="mt-28 max-w-xl"><p className="text-[11px] font-bold uppercase tracking-[0.2em] text-teal-200">Built for accountable work</p><p className="mt-6 font-serif text-6xl leading-[.95] tracking-[-0.06em] xl:text-8xl">Bring your evidence into <em className="text-lime-200">focus.</em></p><p className="mt-7 max-w-lg text-base leading-7 text-teal-100/75">Start with a real document. Keep its version, source trail, analysis state, and editorial history connected.</p></div></div><div className="relative grid gap-3 text-sm text-teal-100/80 sm:grid-cols-3"><span className="flex items-center gap-2"><FileCheck2 size={16} /> Reviewable reports</span><span className="flex items-center gap-2"><LockKeyhole size={16} /> Private workspaces</span><span className="flex items-center gap-2"><ShieldCheck size={16} /> Responsible by design</span></div></section>
    <section className="flex items-center justify-center px-5 py-10 sm:px-10"><div className="w-full max-w-md"><div className="mb-10 lg:hidden"><AzaeronMark /></div><div className="mb-8"><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">Create your account</p><h1 className="mt-3 font-serif text-4xl tracking-[-0.05em] text-slate-950 dark:text-white">Start with a defensible workspace.</h1><p className="mt-3 text-sm leading-6 text-slate-500">Choose how you work, and we will create your personal workspace.</p></div>{error && <div role="alert" className="mb-5"><Notice tone="danger">{error}</Notice></div>}<form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_22px_70px_-44px_rgba(15,23,42,.45)] dark:border-slate-800 dark:bg-slate-900 sm:p-8"><div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">First name<input autoComplete="given-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} placeholder="Azaeron" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal outline-none focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950" /></label><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Last name<input autoComplete="family-name" value={lastName} onChange={(event) => setLastName(event.target.value)} placeholder="Reviewer" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal outline-none focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950" /></label></div><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Work email<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal outline-none focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950" /></label><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Password<input autoComplete="new-password" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 12 characters" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal outline-none focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950" /><span className="mt-2 block text-xs font-normal text-slate-500">Use uppercase, lowercase, number, and special character.</span></label><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Confirm password<input autoComplete="new-password" type="password" required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Repeat your password" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal outline-none focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950" /></label><Button type="submit" disabled={loading} className="w-full py-3.5">{loading ? "Creating your account…" : "Create account"}<ArrowRight size={16} aria-hidden="true" /></Button><p className="flex items-start gap-2 text-xs leading-5 text-slate-500"><CheckCircle2 className="mt-0.5 shrink-0 text-emerald-600" size={14} /> You will be signed in securely after account creation.</p></form><p className="mt-7 text-center text-sm text-slate-500">Already have an account? <Link href="/login" className="font-semibold text-teal-800 hover:underline dark:text-teal-300">Sign in</Link></p></div></section>
  </div></main>;
}
