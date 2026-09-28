"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ChangeEvent, type ReactNode } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  FileCheck2,
  FileText,
  History,
  HelpCircle,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Menu,
  PenLine,
  Plus,
  ScanSearch,
  Settings,
  ShieldCheck,
  Sparkles,
  UserRound,
  WifiOff,
  X,
} from "lucide-react";
import { api, type ApiError } from "@/lib/api";
import { useStore } from "@/lib/store";
import { loadWorkspaceSession, selectWorkspace } from "@/lib/workspace";

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function AzaeronMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-3">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-teal-950 text-sm font-bold text-white shadow-sm shadow-teal-950/20">A</span>
      {!compact && <span className="leading-none"><span className="block font-serif text-[17px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-white">AZAERON</span><span className="mt-1 block text-[9px] font-bold uppercase tracking-[0.2em] text-slate-500">VERITY</span></span>}
    </span>
  );
}

type StatusTone = "production" | "experimental" | "insufficient" | "success" | "warning" | "danger" | "neutral";

const statusStyles: Record<StatusTone, string> = {
  production: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300",
  experimental: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300",
  insufficient: "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300",
  warning: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300",
  danger: "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300",
  neutral: "border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300",
};

export function statusTone(status: string): StatusTone {
  const normalized = status.toLowerCase();
  if (normalized === "production" || normalized === "completed" || normalized === "active" || normalized === "supported") return "production";
  if (normalized === "experimental" || normalized === "processing" || normalized === "queued" || normalized === "partial" || normalized === "partially_supported") return "experimental";
  if (normalized.includes("fail") || normalized.includes("error") || normalized.includes("not_supported")) return "danger";
  if (normalized.includes("insufficient") || normalized.includes("unverifiable") || normalized.includes("not tested")) return "insufficient";
  return "neutral";
}

export function StatusBadge({ status, tone, children }: { status?: string; tone?: StatusTone; children?: ReactNode }) {
  const value = children || status || "Unknown";
  return <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em]", statusStyles[tone || statusTone(String(value))])}>{value}</span>;
}

export function Button({ className, variant = "primary", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  const variants = {
    primary: "bg-teal-950 text-white shadow-sm shadow-teal-950/15 hover:bg-teal-900",
    secondary: "border border-slate-200 bg-white text-slate-800 hover:border-teal-300 hover:text-teal-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
    quiet: "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
    danger: "border border-rose-200 bg-rose-50 text-rose-800 hover:bg-rose-100 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300",
  };
  return <button {...props} className={cn("inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50", variants[variant], className)} />;
}

export function Panel({ title, eyebrow, description, action, children, className }: { title?: string; eyebrow?: string; description?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={cn("rounded-2xl border border-slate-200/90 bg-white shadow-[0_18px_55px_-38px_rgba(15,23,42,0.38)] dark:border-slate-800 dark:bg-slate-900", className)}>
    {(title || eyebrow || description || action) && <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
      <div>{eyebrow && <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">{eyebrow}</p>}{title && <h2 className="mt-1 text-base font-semibold text-slate-950 dark:text-white">{title}</h2>}{description && <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>}</div>{action}
    </div>}
    <div className="p-5">{children}</div>
  </section>;
}

export function WorkflowCard({
  step,
  icon: Icon,
  title,
  outcome,
  detail,
  href,
}: {
  step: string;
  icon: typeof FileText;
  title: string;
  outcome: string;
  detail: string;
  href: string;
}) {
  return <Link href={href} className="group block rounded-2xl border border-slate-200/90 bg-white p-5 shadow-[0_18px_55px_-38px_rgba(15,23,42,0.38)] transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-[0_22px_60px_-36px_rgba(13,148,136,0.32)] focus:outline-none focus:ring-2 focus:ring-teal-600/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-teal-800">
    <div className="flex items-start justify-between gap-4">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-50 text-teal-800 dark:bg-teal-950/50 dark:text-teal-300"><Icon size={19} aria-hidden="true" /></span>
      <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600">{step}</span>
    </div>
    <h2 className="mt-5 text-base font-semibold text-slate-950 dark:text-white">{title}</h2>
    <p className="mt-2 text-sm font-medium leading-6 text-teal-800 dark:text-teal-300">{outcome}</p>
    <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{detail}</p>
    <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-slate-700 group-hover:text-teal-900 dark:text-slate-300 dark:group-hover:text-teal-200">Open workflow <ArrowUpRight size={15} aria-hidden="true" /></span>
  </Link>;
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
    <div>{eyebrow && <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">{eyebrow}</p>}<h1 className="font-serif text-3xl tracking-[-0.04em] text-slate-950 dark:text-white sm:text-4xl">{title}</h1>{description && <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>}</div>{action}
  </header>;
}

export function LoadingState({ label = "Loading workspace data…", rows = 3 }: { label?: string; rows?: number }) {
  return <div className="space-y-3" aria-busy="true" aria-live="polite"><div className="flex items-center gap-3 text-sm text-slate-500"><span className="h-4 w-4 animate-pulse rounded-full bg-teal-200 dark:bg-teal-900" />{label}</div>{Array.from({ length: rows }).map((_, index) => <div key={index} className="h-14 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />)}</div>;
}

export function EmptyState({ icon: Icon = FileText, title, description, action }: { icon?: typeof FileText; title: string; description: string; action?: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-950/30"><span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-teal-50 text-teal-800 dark:bg-teal-950/40 dark:text-teal-300"><Icon size={20} aria-hidden="true" /></span><h2 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>{action && <div className="mt-5 flex justify-center">{action}</div>}</div>;
}

export function ErrorState({ title = "We could not load this view", message, onRetry, permission = false }: { title?: string; message: string; onRetry?: () => void; permission?: boolean }) {
  const Icon = permission ? ShieldCheck : AlertCircle;
  return <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50/70 px-6 py-10 text-center dark:border-rose-900/60 dark:bg-rose-950/20"><Icon className="mx-auto text-rose-700 dark:text-rose-300" size={22} aria-hidden="true" /><h2 className="mt-3 text-base font-semibold text-rose-950 dark:text-rose-100">{permission ? "Permission required" : title}</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-rose-800/80 dark:text-rose-200/80">{message}</p>{onRetry && <Button className="mt-5" variant="secondary" onClick={onRetry}>Try again</Button>}</div>;
}

export function DegradedBanner() {
  const online = useNetworkStatus();
  if (online) return null;
  return <div role="status" className="mb-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200"><WifiOff size={18} className="mt-0.5 shrink-0" aria-hidden="true" /><div><p className="font-semibold">You are offline</p><p className="mt-1 text-xs leading-5 opacity-80">Saved workspace data remains visible where available. New analysis and uploads will resume when the connection returns.</p></div></div>;
}

export function useNetworkStatus() {
  const [online, setOnline] = useState(() => typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => { window.removeEventListener("online", onOnline); window.removeEventListener("offline", onOffline); };
  }, []);
  return online;
}

export function isPermissionError(error: unknown) {
  return error instanceof Error && "status" in error && [401, 403].includes((error as ApiError).status);
}

const navItems = [
  { href: "/dashboard", label: "Home", icon: LayoutDashboard },
  { href: "/ai", label: "Azaeron AI", icon: Sparkles },
  { href: "/humaniser", label: "AI Humaniser", icon: PenLine },
  { href: "/detector", label: "AI Detector", icon: ScanSearch },
  { href: "/plagiarism", label: "Plagiarism Checker", icon: FileCheck2 },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/history", label: "History", icon: History },
];

export function WorkspaceSwitcher({ mobile = false }: { mobile?: boolean }) {
  const { organizations, currentOrg, organizationState } = useStore();
  const [switching, setSwitching] = useState(false);
  const handleChange = async (event: ChangeEvent<HTMLSelectElement>) => {
    const next = organizations.find((organization) => organization.id === event.target.value);
    if (!next || next.id === currentOrg?.id) return;
    setSwitching(true);
    try {
      await selectWorkspace(next);
    } catch {
      // The shell displays the failure and revalidates scope on retry.
    } finally { setSwitching(false); }
  };
  return <div className={cn("block", mobile ? "px-3" : "px-3")}><span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">Workspace</span>{organizations.length ? <><span className="relative block"><select aria-label="Active workspace" value={currentOrg?.id || ""} onChange={handleChange} disabled={switching || organizationState === "selecting"} className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 pr-9 text-sm font-semibold text-slate-800 outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"><option value="">Select workspace</option>{organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}</select><ChevronDown size={15} className="pointer-events-none absolute right-3 top-3 text-slate-500" aria-hidden="true" /></span>{switching && <span className="mt-1 block text-[11px] text-teal-700 dark:text-teal-300">Switching workspace…</span>}</> : <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-3 py-3 dark:border-slate-700 dark:bg-slate-950/50"><p className="text-xs font-semibold text-slate-700 dark:text-slate-200">No workspace yet</p><p className="mt-1 text-[11px] leading-5 text-slate-500">Create a workspace from the card on this page.</p><Link href="/settings?tab=workspace" className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-teal-800 hover:text-teal-950 dark:text-teal-300"><Plus size={13} aria-hidden="true" /> Create workspace</Link></div>}</div>;
}

export function WorkspaceSetup({ compact = false }: { compact?: boolean }) {
  const { organizations, setOrganizations } = useStore();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const createWorkspace = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Give your workspace a name before continuing.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const created = await api.createOrganization(trimmedName, description.trim() || undefined);
      const workspace = { ...created, role: "owner" };
      setOrganizations([...organizations, workspace]);
      await selectWorkspace(workspace);
      setName("");
      setDescription("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create workspace.");
    } finally {
      setSaving(false);
    }
  };

  return <form onSubmit={createWorkspace} className={cn("rounded-2xl border border-teal-200 bg-teal-50/70 dark:border-teal-900/70 dark:bg-teal-950/20", compact ? "p-4" : "p-6")}>
    <div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal-950 text-white"><Plus size={18} aria-hidden="true" /></span><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">First step</p><h2 className="mt-1 text-base font-semibold text-teal-950 dark:text-teal-50">Create your workspace</h2><p className="mt-1 text-sm leading-6 text-teal-900/70 dark:text-teal-100/70">Your documents, evidence, and team access will be scoped here.</p></div></div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold text-slate-700 dark:text-slate-200">Workspace name<input autoComplete="organization" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Acme Research Lab" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 dark:border-slate-700 dark:bg-slate-900 dark:text-white" /></label><label className="text-sm font-semibold text-slate-700 dark:text-slate-200">Description <span className="font-normal text-slate-600">optional</span><input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What is this workspace for?" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20 dark:border-slate-700 dark:bg-slate-900 dark:text-white" /></label></div>
    {error && <p role="alert" className="mt-3 text-sm font-medium text-rose-700 dark:text-rose-300">{error}</p>}
    <div className="mt-5 flex flex-wrap items-center gap-3"><Button type="submit" disabled={saving}><CheckCircle2 size={16} aria-hidden="true" /> {saving ? "Creating workspace…" : "Create workspace"}</Button><span className="text-xs text-slate-500">You become the workspace owner.</span></div>
  </form>;
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, currentOrg, organizations, organizationState, organizationError, logout, isLoading } = useStore();
  const [logoutError, setLogoutError] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mobileViewport, setMobileViewport] = useState(false);
  const navigationRef = useRef<HTMLElement>(null);
  const closeNavigationRef = useRef<HTMLButtonElement>(null);
  const modalOpen = mobileViewport && mobileOpen;

  useEffect(() => {
    const query = window.matchMedia("(max-width: 1023px)");
    const update = () => {
      setMobileViewport(query.matches);
      if (!query.matches) setMobileOpen(false);
    };
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!modalOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    closeNavigationRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileOpen(false);
      }
      if (event.key !== "Tab" || !navigationRef.current) return;
      const controls = Array.from(navigationRef.current.querySelectorAll<HTMLElement>("a, button, select, input, [tabindex]:not([tabindex='-1'])"))
        .filter((control) => control.getClientRects().length > 0 && !control.hasAttribute("disabled"));
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !navigationRef.current.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !navigationRef.current.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      requestAnimationFrame(() => previousFocus?.isConnected && previousFocus.focus());
    };
  }, [modalOpen]);

  useEffect(() => {
    if (!isLoading) return;
    void loadWorkspaceSession().then((profile) => {
      if (!profile.onboarding_completed) router.replace("/onboarding");
    }).catch((error) => {
      if (error?.status === 401) router.replace("/login");
    });
  }, [isLoading, router]);

  const retryWorkspace = () => {
    void loadWorkspaceSession().catch((error) => {
      if (error?.status === 401) router.replace("/login");
    });
  };

  const handleLogout = async () => {
    setLogoutError("");
    try { await api.logout(); logout(true); router.push("/"); }
    catch { setLogoutError("Sign-out could not reach the server. Your session is still open; reconnect and try again."); }
  };
  if (isLoading) return <div className="grid min-h-screen place-items-center bg-[#f7faf8] dark:bg-slate-950"><div className="text-center"><AzaeronMark /><div className="mt-6 h-1.5 w-40 animate-pulse rounded-full bg-teal-100 dark:bg-teal-900" /><p className="mt-3 text-sm text-slate-500">Opening your workspace…</p></div></div>;
  if (!user) return <div className="grid min-h-screen place-items-center bg-[#f7faf8] px-5 dark:bg-slate-950"><div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-[0_24px_80px_-48px_rgba(15,23,42,.4)] dark:border-slate-800 dark:bg-slate-900"><AzaeronMark /><div className="mx-auto mt-10 grid h-12 w-12 place-items-center rounded-2xl bg-teal-50 text-teal-800 dark:bg-teal-950/50 dark:text-teal-300"><LockKeyhole size={22} aria-hidden="true" /></div><h1 className="mt-5 font-serif text-3xl tracking-[-0.04em] text-slate-950 dark:text-white">Sign in to continue</h1><p className="mt-3 text-sm leading-6 text-slate-500">Your workspace is protected. Start a secure session before opening tenant-scoped documents and evidence.</p><div className="mt-7 flex flex-col gap-3 sm:flex-row sm:justify-center"><Link href="/login"><Button>Sign in <ArrowUpRight size={15} aria-hidden="true" /></Button></Link><Link href="/register"><Button variant="secondary">Create account</Button></Link></div>{organizationError && <p role="alert" className="mt-5 text-xs text-rose-700 dark:text-rose-300">{organizationError}</p>}</div></div>;

  return <div className="min-h-screen bg-[#f7faf8] text-slate-900 dark:bg-slate-950 dark:text-slate-100">
    <div className={cn("fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-[2px] lg:hidden", mobileOpen ? "block" : "hidden")} onClick={() => setMobileOpen(false)} aria-hidden="true" />
    <aside id="workspace-navigation" ref={navigationRef} role={modalOpen ? "dialog" : undefined} aria-modal={modalOpen || undefined} aria-hidden={mobileViewport && !mobileOpen || undefined} inert={mobileViewport && !mobileOpen} className={cn("fixed inset-y-0 left-0 z-50 flex w-[286px] flex-col border-r border-slate-200 bg-white transition-transform duration-200 dark:border-slate-800 dark:bg-slate-900 lg:visible lg:translate-x-0", mobileOpen ? "visible translate-x-0" : "invisible -translate-x-full")} aria-label="Primary navigation">
      <div className="flex h-[76px] items-center justify-between border-b border-slate-100 px-5 dark:border-slate-800"><Link href="/dashboard" aria-label="AZAERON dashboard" onClick={() => setMobileOpen(false)}><AzaeronMark /></Link><button ref={closeNavigationRef} type="button" className="grid h-9 w-9 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18} /></button></div>
      <div className="px-3 py-5"><WorkspaceSwitcher /></div>
      <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-5" aria-label="Workspace navigation"><div className="space-y-1">{navItems.map((item) => { const Icon = item.icon; const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`)) || (item.href === "/plagiarism" && pathname === "/similarity") || (item.href === "/documents" && ["/write", "/check", "/upload"].includes(pathname)); return <Link key={item.href} href={item.href} onClick={() => setMobileOpen(false)} aria-current={active ? "page" : undefined} className={cn("group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors", active ? "bg-teal-50 text-teal-950 dark:bg-teal-950/50 dark:text-teal-200" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white")}><Icon size={17} strokeWidth={active ? 2.3 : 1.8} aria-hidden="true" /><span>{item.label}</span>{active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-teal-700 dark:bg-teal-300" />}</Link>; })}</div></nav>
      <div className="border-t border-slate-100 p-3 dark:border-slate-800"><Link href="/settings" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"><Settings size={17} aria-hidden="true" /> Settings</Link><Link href="/help" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"><HelpCircle size={17} aria-hidden="true" /> Help</Link><Link href="/settings?tab=profile" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"><UserRound size={17} aria-hidden="true" /> Account</Link><button type="button" onClick={handleLogout} className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"><LogOut size={17} aria-hidden="true" /> Sign out</button>{logoutError && <p role="alert" className="mt-2 px-3 text-xs text-rose-700 dark:text-rose-300">{logoutError}</p>}</div>
    </aside>
    <div className="lg:pl-[286px]" inert={modalOpen}><header className="sticky top-0 z-30 flex h-[76px] items-center justify-between border-b border-slate-200/80 bg-[#f7faf8]/90 px-4 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/90 sm:px-6 lg:px-10"><div className="flex items-center gap-3"><button type="button" onClick={() => setMobileOpen(true)} className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-700 lg:hidden dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={modalOpen}><Menu size={19} /></button><div className="hidden items-center gap-2 text-xs font-medium text-slate-500 sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Secure workspace</div></div><div className="flex items-center gap-3"><Link href="/write" className="hidden items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold text-teal-900 hover:bg-teal-50 sm:inline-flex dark:text-teal-200 dark:hover:bg-teal-950/40"><PenLine size={15} /> Document Editor</Link><div className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-950 text-xs font-bold text-white" role="img" aria-label={`Signed in as ${user.email}`}>{(user.first_name?.[0] || user.email[0] || "A").toUpperCase()}</div></div></header><main className="mx-auto max-w-[1440px] px-4 py-7 sm:px-6 lg:px-10 lg:py-10"><DegradedBanner />{organizationState === "selecting" ? <LoadingState label="Switching workspace…" /> : organizationState === "selection_failed" ? <ErrorState message={organizationError || "We could not confirm your workspace. Retry or select another workspace from the sidebar."} onRetry={retryWorkspace} /> : !currentOrg && !pathname.startsWith("/settings") ? <div className="space-y-5"><PageHeader eyebrow="Your workspace" title="Start with your own workspace" description="Create a workspace here and continue to your document. Your account and settings remain available." />{organizations.length > 0 && <Notice tone="warning">Choose a workspace from the sidebar, or create one below.</Notice>}<WorkspaceSetup /></div> : <div key={currentOrg?.id || "account"}>{children}</div>}</main></div>
  </div>;
}

export function ModuleNav({ documentId, versionId }: { documentId?: string; versionId?: string }) {
  if (!documentId) return null;
  return <details className="mb-6 rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900"><summary className="cursor-pointer text-sm font-semibold text-teal-900 dark:text-teal-200">Advanced Analysis</summary><nav aria-label="Document analysis navigation" className="mt-3 flex gap-2 overflow-x-auto border-t border-slate-100 pt-3 text-sm dark:border-slate-800">{[
    ["Report", `/documents/${documentId}`], ["Similarity", `/similarity?document=${documentId}`], ["Graph", `/evidence-graph?document=${documentId}`], ["Sources", `/sources?document=${documentId}`], ["Citations", `/citations?document=${documentId}`], ["Authorship", `/authorship?document=${documentId}`], ["Provenance", `/provenance?document=${documentId}`],
  ].map(([label, href]) => <Link key={href} href={versionId ? `${href}${href.includes("?") ? "&" : "?"}version=${encodeURIComponent(versionId)}` : href} className="whitespace-nowrap rounded-lg px-3 py-2 font-semibold text-slate-500 hover:bg-slate-100 hover:text-teal-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-teal-200">{label}</Link>)}</nav></details>;
}

export function Notice({ children, tone = "neutral" }: { children: ReactNode; tone?: StatusTone }) {
  const Icon = tone === "danger" ? AlertCircle : tone === "warning" ? AlertTriangle : tone === "production" ? ShieldCheck : Sparkles;
  return <div className={cn("flex items-start gap-3 rounded-xl border px-4 py-3 text-sm", statusStyles[tone])}><Icon size={17} className="mt-0.5 shrink-0" aria-hidden="true" /><div className="leading-6">{children}</div></div>;
}
