"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button, Notice } from "@/components/design-system";

export function IdentityLink({ mode }: { mode: "request" | "reset" | "verify" }) {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (value) {
      // Synchronize a one-time token from the external browser URL, then remove it.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setToken(value);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  const title = mode === "request" ? "Reset your password" : mode === "reset" ? "Choose a new password" : "Verify your email";
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = mode === "request" ? await api.requestPasswordReset(email) : mode === "reset" ? await api.resetPassword(token, password) : await api.confirmEmail(token);
      setMessage(result.message); setDone(true); setToken(""); setPassword("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to complete this request."); }
    finally { setBusy(false); }
  }
  return <main className="flex min-h-screen items-center justify-center bg-slate-50 px-5 py-10 dark:bg-slate-950"><section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
    <h1 className="text-2xl font-semibold">{title}</h1>
    {error && <div role="alert" className="mt-4"><Notice tone="danger">{error}</Notice></div>}
    <p role="status" className="mt-4 text-sm">{message}</p>
    {!done && <form onSubmit={submit} className="mt-4 space-y-4">
      {mode === "request" && <label className="block text-sm font-semibold">Account email<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2" /></label>}
      {mode === "reset" && <label className="block text-sm font-semibold">New password<input aria-label="New password" aria-describedby="reset-password-requirements" type="password" autoComplete="new-password" required minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2" /><span id="reset-password-requirements" className="mt-2 block text-xs font-normal">Use uppercase and lowercase letters, a number, and a symbol; at most 72 UTF-8 bytes.</span></label>}
      {mode !== "request" && !token && <p className="text-sm">Open the complete link from your email. If you refreshed this page, reopen that link.</p>}
      <Button type="submit" disabled={busy || mode !== "request" && !token}>{mode === "request" ? "Send reset link" : mode === "reset" ? "Set new password" : "Verify email"}</Button>
    </form>}
    <Link href="/login" className="mt-6 inline-block text-sm font-semibold text-teal-800 underline dark:text-teal-300">Return to sign in</Link>
  </section></main>;
}
