"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type ApiKeyMetadata, type ApiKeyScope, type CreatedApiKey } from "@/lib/api";
import { Button, Notice } from "@/components/design-system";

const scopes: ApiKeyScope[] = ["text:analyze", "text:refine", "text:verify", "documents:read", "documents:write", "usage:read", "ai:chat"];
const fieldClass = "mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-950";

export function ApiKeys({ organizationId }: { organizationId: string }) {
  const [keys, setKeys] = useState<ApiKeyMetadata[]>([]);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<ApiKeyScope[]>(["documents:read"]);
  const [expiry, setExpiry] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const secretField = useRef<HTMLTextAreaElement>(null);
  const mounted = useRef(false);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let active = true;
    api.getApiKeys(offset).then((rows) => { if (active) setKeys(rows); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load keys."); });
    return () => { active = false; };
  }, [organizationId, offset, refresh]);
  useEffect(() => { if (secret) secretField.current?.focus(); }, [secret]);

  async function mutate(action: () => Promise<CreatedApiKey | void>, success: string) {
    setBusy(true); setError(""); setMessage(""); setSecret("");
    try {
      const result = await action();
      if (!mounted.current) return;
      if (result) setSecret(result.secret);
      setMessage(success); setRefresh((value) => value + 1);
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "Unable to update key.");
    } finally { if (mounted.current) setBusy(false); }
  }
  function create(event: FormEvent) {
    event.preventDefault();
    void mutate(() => api.createApiKey({ name, scopes: selected, expires_at: expiry ? new Date(expiry).toISOString() : null }), "API key created. Save the secret now.");
  }

  return <section aria-labelledby="api-keys-heading" className="mt-8 border-t border-slate-200 pt-6 dark:border-slate-800">
    <h2 id="api-keys-heading" className="text-base font-semibold">Workspace API keys</h2>
    <p className="mt-2 text-sm text-slate-500">Administrators can create credentials for this workspace. Keys retain the issuing account’s permissions. Model-dependent features remain unavailable until approved models are deployed.</p>
    {error && <div role="alert" className="mt-3"><Notice tone="danger">{error}</Notice></div>}
    <p role="status" className="mt-3 text-sm">{message}</p>
    {secret && <div className="my-4 rounded-lg border border-amber-400 p-4">
      <label className="block text-sm font-semibold">New API key — shown once<textarea aria-label="New API key — shown once" ref={secretField} readOnly value={secret} className={fieldClass + " break-all font-mono"} rows={4} onFocus={(event) => event.target.select()} /></label>
      <p className="my-2 text-sm">Store this secret securely. It cannot be retrieved again. Closing or leaving this view clears it.</p>
      <Button variant="secondary" onClick={() => setSecret("")}>I saved the secret</Button>
    </div>}
    <form onSubmit={create} className="mt-4 space-y-4">
      <label className="block text-sm font-semibold">Key name<input className={fieldClass} value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} autoComplete="off" /></label>
      <fieldset><legend className="text-sm font-semibold">Allowed operations</legend><div className="mt-2 grid gap-2 sm:grid-cols-2">{scopes.map((scope) => <label key={scope} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(scope)} onChange={(event) => setSelected(event.target.checked ? [...selected, scope] : selected.filter((value) => value !== scope))} />{scope}</label>)}</div></fieldset>
      <label className="block text-sm font-semibold">Expires at (optional, local time)<input className={fieldClass} type="datetime-local" value={expiry} onChange={(event) => setExpiry(event.target.value)} /></label>
      <Button type="submit" disabled={busy || !selected.length}>Create API key</Button>
    </form>
    <ul className="mt-6 space-y-3" aria-label="API keys">{keys.map((key) => <li key={key.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="break-words font-semibold">{key.name} <span className="text-xs font-normal">({key.key_prefix}…)</span></p>
      <p className="mt-1 break-words text-sm">{key.scopes.join(", ")}</p>
      <p className="mt-1 text-xs">{!key.is_active ? "Revoked" : key.expires_at && new Date(key.expires_at) <= new Date() ? "Expired" : "Active"} · Last used: {key.last_used_at ? new Date(key.last_used_at).toLocaleString() : "Never"} · Expires: {key.expires_at ? new Date(key.expires_at).toLocaleString() : "No expiry"}</p>
      {key.is_active && <div className="mt-3 flex flex-wrap gap-2"><Button variant="secondary" disabled={busy} aria-label={`Rotate ${key.name}`} onClick={() => void mutate(() => api.rotateApiKey(key.id), "Key rotated. The previous secret no longer works.")}>Rotate</Button><Button variant="secondary" disabled={busy} aria-label={`Revoke ${key.name}`} onClick={() => void mutate(() => api.revokeApiKey(key.id), "API key revoked.")}>Revoke</Button></div>}
    </li>)}</ul>
    <div className="mt-3 flex gap-2"><Button variant="secondary" disabled={!offset || busy} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous keys</Button><Button variant="secondary" disabled={keys.length < 50 || busy} onClick={() => setOffset(offset + 50)}>Next keys</Button></div>
  </section>;
}
