"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CheckCircle2, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { AzaeronMark, Button, Notice } from "@/components/design-system";
import { loadWorkspaceSession, workspaceHome } from "@/lib/workspace";

export default function LoginPage() {
  const router = useRouter();
  const [registered, setRegistered] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // The query string is an external browser signal used for a one-time
    // confirmation message after registration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRegistered(new URLSearchParams(window.location.search).has("registered"));
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(email.trim(), password, mfaRequired ? mfaCode : undefined);
      const profile = await loadWorkspaceSession();
      router.push(workspaceHome(profile));
    } catch (reason) {
      if (reason instanceof ApiError && ["mfa_required", "mfa_invalid"].includes(reason.code || "")) setMfaRequired(true);
      setError(reason instanceof Error ? reason.message : "We could not sign you in.");
    } finally {
      setLoading(false);
    }
  };

  return <main className="min-h-screen bg-[#f7faf8] text-slate-950 dark:bg-slate-950 dark:text-white"><div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(430px,0.78fr)]">
    <section className="relative hidden overflow-hidden bg-teal-950 p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-16"><div className="absolute inset-0 opacity-40" style={{ backgroundImage: "linear-gradient(rgba(204,240,216,.09) 1px, transparent 1px), linear-gradient(90deg, rgba(204,240,216,.09) 1px, transparent 1px)", backgroundSize: "54px 54px" }} /><div className="relative"><AzaeronMark /><div className="mt-28 max-w-xl"><p className="text-[11px] font-bold uppercase tracking-[0.2em] text-teal-200">Evidence-first writing intelligence</p><p className="mt-6 font-serif text-6xl leading-[.95] tracking-[-0.06em] xl:text-8xl">A clearer path from draft to <em className="text-lime-200">decision.</em></p><p className="mt-7 max-w-lg text-base leading-7 text-teal-100/75">A serious workspace for document review, source intelligence, provenance, and responsible editorial improvement.</p></div></div><div className="relative grid gap-3 text-sm text-teal-100/80 sm:grid-cols-3"><span className="flex items-center gap-2"><ShieldCheck size={16} /> Tenant-scoped</span><span className="flex items-center gap-2"><LockKeyhole size={16} /> Secure by default</span><span className="flex items-center gap-2"><CheckCircle2 size={16} /> Evidence linked</span></div></section>
    <section className="flex items-center justify-center px-5 py-10 sm:px-10"><div className="w-full max-w-md"><div className="mb-10 lg:hidden"><AzaeronMark /></div><div className="mb-8"><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">Welcome back</p><h1 className="mt-3 font-serif text-4xl tracking-[-0.05em] text-slate-950 dark:text-white">Sign in to your workspace.</h1><p className="mt-3 text-sm leading-6 text-slate-500">Continue to your tenant-scoped documents and evidence.</p></div>{registered && <div className="mb-5"><Notice tone="success"><span className="flex items-center gap-2"><CheckCircle2 size={16} /> Account created. Sign in to continue.</span></Notice></div>}{error && <div role="alert" className="mb-5"><Notice tone="danger">{error}</Notice></div>}<form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_22px_70px_-44px_rgba(15,23,42,.45)] dark:border-slate-800 dark:bg-slate-900 sm:p-8"><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Work email<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal text-slate-950 outline-none transition focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950 dark:text-white" /></label><label className="block text-sm font-semibold text-slate-800 dark:text-slate-200">Password<input autoComplete="current-password" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 text-sm font-normal text-slate-950 outline-none transition focus:border-teal-600 focus:bg-white focus:ring-4 focus:ring-teal-600/10 dark:border-slate-700 dark:bg-slate-950 dark:text-white" /></label>{mfaRequired && <label className="block text-sm font-semibold">Authenticator or recovery code<input autoFocus autoComplete="one-time-code" required value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-3.5 py-3 text-sm dark:border-slate-700 dark:bg-slate-950" /></label>}<Button type="submit" disabled={loading} className="w-full py-3.5">{loading ? "Opening workspace…" : "Sign in"}<ArrowRight size={16} aria-hidden="true" /></Button><p className="text-center text-xs leading-5 text-slate-500">Sessions are protected by HttpOnly cookies and refresh rotation.</p></form><p className="mt-4 text-center text-sm"><Link href="/forgot-password" className="font-semibold text-teal-800 hover:underline dark:text-teal-300">Forgot your password?</Link></p><p className="mt-7 text-center text-sm text-slate-500">New to AZAERON? <Link href="/register" className="font-semibold text-teal-800 hover:underline dark:text-teal-300">Create an account</Link></p></div></section>
  </div></main>;
}
