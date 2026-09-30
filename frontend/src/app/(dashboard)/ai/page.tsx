"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AgentPanel } from "@/components/agent-panel";
import { LoadingState } from "@/components/design-system";
import { useStore } from "@/lib/store";

function AIWorkspace() {
  const { currentOrg, user } = useStore();
  const params = useSearchParams();
  const router = useRouter();
  const requested = params.get("conversation");
  const conversationId = requested && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(requested) ? requested : undefined;
  const select = useCallback((id?: string) => router.replace(id ? `/ai?conversation=${encodeURIComponent(id)}` : "/ai", { scroll: false }), [router]);
  return <AgentPanel key={`${currentOrg?.id}:${user?.id}`} initialConversationId={conversationId} onConversationChange={select} />;
}

export default function AzaeronAIPage() {
  return <div><header className="mb-5"><p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.17em] text-teal-700 dark:text-teal-300">Workspace chat</p><h1 className="font-serif text-3xl tracking-[-0.04em] text-slate-950 dark:text-white sm:text-4xl">Azaeron AI</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">Ask a question or work through a document, with a clear record of your conversation.</p></header><Suspense fallback={<LoadingState label="Opening conversations…" />}><AIWorkspace /></Suspense></div>;
}
