"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Button, Notice } from "@/components/design-system";

type Session = Awaited<ReturnType<typeof api.getSessions>>[number];
const field = "mt-2 w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm";

export function IdentitySecurity() {
  const { user, setUser, logout } = useStore();
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrollment, setEnrollment] = useState<{ secret: string; expires_at: string } | null>(null);
  const [recovery, setRecovery] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [refresh, setRefresh] = useState(0);
  const secretField = useRef<HTMLTextAreaElement>(null);
  const live = useRef(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => {
    let active = true;
    api.getSessions().then((result) => { if (active) setSessions(result); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load sessions."); });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => { if (recovery.length || enrollment) secretField.current?.focus(); }, [recovery, enrollment]);

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); if (live.current) setRefresh((value) => value + 1); }
    catch (reason) { if (live.current) setError(reason instanceof Error ? reason.message : "Unable to complete security change."); }
    finally { if (live.current) { setBusy(false); setPassword(""); setCode(""); } }
  }
  async function reloadProfile() { const profile = await api.getMe(); if (live.current) setUser(profile); }
  const secret = recovery.length ? recovery.join("\n") : enrollment?.secret || "";

  return <section aria-labelledby="identity-heading">
    <h2 id="identity-heading" className="text-base font-semibold">Account security</h2>
    {error && <div role="alert" className="mt-3"><Notice tone="danger">{error}</Notice></div>}
    <p role="status" className="mt-3 text-sm">{message}</p>
    <div className="mt-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-sm">Email: {user?.is_verified ? "Verified" : "Not verified"}</p>
      {!user?.is_verified && <Button variant="secondary" disabled={busy} onClick={() => void perform(async () => { const result = await api.requestVerification(); if (live.current) setMessage(result.message); })}>Send verification email</Button>}
      <Button variant="secondary" disabled={busy} onClick={() => void perform(reloadProfile)}>Refresh verification status</Button>
    </div>
    <div className="mt-5 space-y-4">
      <h3 className="font-semibold">Multi-factor authentication: {user?.mfa_enabled ? "enabled" : "not enabled"}</h3>
      <p className="text-sm text-slate-500">Use a TOTP authenticator. Recovery codes work once each. Enabling or disabling MFA revokes other sessions.</p>
      {secret && <div className="rounded-lg border border-amber-400 p-4"><label className="block text-sm font-semibold">{recovery.length ? "Recovery codes — save now" : "Authenticator setup secret"}<textarea aria-label={recovery.length ? "Recovery codes — save now" : "Authenticator setup secret"} ref={secretField} readOnly value={secret} rows={recovery.length ? 10 : 2} className={field + " font-mono"} onFocus={(event) => event.target.select()} /></label><p className="mt-2 text-xs">{recovery.length ? "Keep these codes offline. They cannot be retrieved again." : `Enter this secret in your authenticator, then confirm a six-digit code. Enrollment expires ${new Date(enrollment!.expires_at).toLocaleTimeString()}.`}</p>{recovery.length > 0 && <Button variant="secondary" onClick={() => setRecovery([])}>I saved the recovery codes</Button>}</div>}
      <label className="block text-sm font-semibold">Current password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className={field} /></label>
      {(user?.mfa_enabled || enrollment) && <label className="block text-sm font-semibold">Authenticator or recovery code<input autoComplete="one-time-code" value={code} onChange={(event) => setCode(event.target.value)} className={field} /></label>}
      <div className="flex flex-wrap gap-2">
        {!user?.mfa_enabled && !enrollment && <Button disabled={busy || !password} onClick={() => void perform(async () => { const result = await api.enrollMfa(password); if (live.current) { setEnrollment(result); setRecovery([]); } })}>Set up MFA</Button>}
        {enrollment && <Button disabled={busy || !/^\d{6}$/.test(code)} onClick={() => void perform(async () => { const result = await api.confirmMfa(code); if (live.current) { setEnrollment(null); setRecovery(result.recovery_codes); setMessage(result.message); } await reloadProfile(); })}>Confirm authenticator</Button>}
        {enrollment && <Button variant="secondary" disabled={busy} onClick={() => { setEnrollment(null); setCode(""); }}>Cancel setup</Button>}
        {user?.mfa_enabled && <><Button variant="secondary" disabled={busy || !password || !code} onClick={() => void perform(async () => { const result = await api.manageMfa("recovery", password, code); if (live.current) { setRecovery(result.recovery_codes || []); setMessage("Previous recovery codes were replaced."); } })}>Replace recovery codes</Button><Button variant="secondary" disabled={busy || !password || !code} onClick={() => void perform(async () => { const result = await api.manageMfa("disable", password, code); if (live.current) { setRecovery([]); setMessage(result.message || "MFA disabled."); } await reloadProfile(); })}>Disable MFA</Button></>}
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void perform(async () => { await api.changePassword(password, newPassword, user?.mfa_enabled ? code : undefined); if (live.current) { setNewPassword(""); logout(true); router.push("/login"); } }); }} className="border-t border-slate-200 pt-4 dark:border-slate-800">
        <label className="block text-sm font-semibold">New password<input type="password" autoComplete="new-password" required minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} className={field} /></label>
        <p className="my-2 text-xs text-slate-500">Use uppercase/lowercase letters, a number and a symbol; at most 72 UTF-8 bytes. Changing your password signs out all sessions.</p>
        <Button disabled={busy || !password || !!user?.mfa_enabled && !code} type="submit">Change password</Button>
      </form>
    </div>
    <div className="mt-6 border-t border-slate-200 pt-5 dark:border-slate-800"><h3 className="font-semibold">Active sessions</h3>
      <p className="mt-2 text-xs text-slate-500">Device descriptions come from the browser and are informational.</p>
      <ul className="my-4 space-y-3">{sessions.map((session) => <li key={session.id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800"><p className="break-words">{session.current ? "This session" : "Other session"} · {session.user_agent || "Unknown device"}</p><p className="mt-1 text-xs">Address: {session.ip_address || "Unknown"} · Expires {new Date(session.expires_at).toLocaleString()}</p>{!session.current && <Button variant="secondary" disabled={busy} aria-label={`Revoke session from ${session.ip_address || "unknown address"}`} onClick={() => void perform(async () => { await api.revokeSession(session.id); if (live.current) setMessage("Session revoked."); })}>Revoke session</Button>}</li>)}</ul>
      <Button variant="secondary" disabled={busy || !sessions.some((session) => !session.current)} onClick={() => void perform(async () => { await api.revokeSession("others"); if (live.current) setMessage("Other sessions revoked."); })}>Revoke all other sessions</Button>
    </div>
  </section>;
}
