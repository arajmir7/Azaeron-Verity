import Link from "next/link";
import { ArrowUpRight, LockKeyhole, PenLine, Sparkles } from "lucide-react";
import { Button, PageHeader, Panel, StatusBadge } from "@/components/design-system";

export default function AzaeronAIPage() {
  return <div className="mx-auto max-w-4xl">
    <PageHeader eyebrow="Azaeron AI" title="Your writing partner" description="Ask questions, explore ideas, and work with documents in one private workspace." />
    <Panel className="overflow-hidden" title="Azaeron AI" action={<StatusBadge status="Unavailable" />}>
      <div className="mx-auto max-w-xl py-10 text-center"><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-teal-50 text-teal-900 dark:bg-teal-950 dark:text-teal-200"><LockKeyhole size={25} aria-hidden="true" /></span><h2 className="mt-5 text-xl font-semibold">Private AI is being prepared</h2><p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">An approved self-hosted writing model is not available in this environment. Questions and documents will not be sent to an outside AI provider, and we will not invent a response.</p><div className="mt-6 flex flex-wrap justify-center gap-3"><Link href="/write"><Button><PenLine size={16} aria-hidden="true" /> Open Document Editor</Button></Link><Link href="/humaniser"><Button variant="secondary"><Sparkles size={16} aria-hidden="true" /> Review writing suggestions <ArrowUpRight size={15} aria-hidden="true" /></Button></Link></div></div>
    </Panel>
  </div>;
}
