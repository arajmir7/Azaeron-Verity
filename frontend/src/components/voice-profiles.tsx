"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { type Attachment, agentButton as button, agentInput as input } from "@/lib/agent";

type Profile = { id: string; name: string };

export function VoiceProfiles({ sample, selected, onSelect, disabled }: { sample?: Attachment; selected: string; onSelect: (id: string) => void; disabled: boolean }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [name, setName] = useState("");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void api.agent<{ items: Profile[] }>("/voice-profiles").then((result) => { if (alive) setProfiles(result.items); }).catch(() => { if (alive) setError("Voice profiles could not be loaded."); });
    return () => { alive = false; };
  }, []);
  async function save() {
    if (!sample || !approved) return;
    setBusy(true); setError("");
    try {
      const profile = await api.agent<Profile>("/voice-profiles", { method: "POST", body: JSON.stringify({ name, samples: [sample], approved }) });
      setProfiles((items) => [profile, ...items]); onSelect(profile.id); setName(""); setApproved(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Profile could not be saved."); }
    finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError("");
    try { await api.agent(`/voice-profiles/${selected}`, { method: "DELETE" }); setProfiles((items) => items.filter((profile) => profile.id !== selected)); onSelect(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Profile could not be removed."); }
    finally { setBusy(false); }
  }
  return <details className="mb-4 text-sm"><summary className="cursor-pointer font-medium">VoiceLock · optional writing style</summary>
    <p className="my-2 text-xs leading-5 text-slate-500">Use an approved sample you own, with at least 100 words. The profile records style statistics. Generation still requires an approved private model; style fidelity has not been benchmarked.</p>
    <label className="block">Writing voice<select className={`${input} my-2`} disabled={disabled || busy} value={selected} onChange={(event) => onSelect(event.target.value)}><option value="">No voice profile</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></label>
    {selected && <button type="button" className={button} disabled={disabled || busy} onClick={() => void remove()}>Remove selected profile</button>}
    <label className="mt-3 block">New profile name<input className={`${input} my-2`} maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label>
    <label className="mb-2 flex items-start gap-2 text-xs"><input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} />I own and approve the attached saved version as a writing sample.</label>
    <button type="button" className={button} disabled={disabled || busy || !approved || !name.trim() || !sample} onClick={() => void save()}>Create voice profile</button>
    {error && <p role="alert" className="mt-2 text-sm text-amber-800 dark:text-amber-200">{error}</p>}
  </details>;
}
