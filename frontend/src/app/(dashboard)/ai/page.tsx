"use client";

import { AgentPanel } from "@/components/agent-panel";
import { PageHeader } from "@/components/design-system";
import { useStore } from "@/lib/store";

export default function AzaeronAIPage() {
  const { currentOrg, user } = useStore();
  return <div><PageHeader eyebrow="Azaeron AI" title="Your writing partner" description="Create with context. Review the evidence. Approve each document change." /><AgentPanel key={`${currentOrg?.id}:${user?.id}`} /></div>;
}
