import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { PageHeader, Panel } from "@/components/design-system";

const topics = [
  { title: "Start a document", body: "Paste text or upload a PDF, DOCX, TXT, Markdown, or HTML file. Azaeron keeps a private version of accepted content.", href: "/check", label: "Create a document" },
  { title: "Improve a draft", body: "The Document Editor saves revisions and lets you review limited editorial suggestions before accepting them. Generative rewriting is not available yet.", href: "/write", label: "Open editor" },
  { title: "Interpret an AI check", body: "Writing signals are experimental. An uncertain result means the system lacks validated evidence; it is not proof of human or AI authorship.", href: "/detector", label: "Open detector" },
  { title: "Understand a similarity check", body: "Matches cover only indexed sources available to your workspace. A match alone does not establish plagiarism.", href: "/plagiarism", label: "Open checker" },
];

export default function HelpPage() {
  return <div className="mx-auto max-w-4xl"><PageHeader eyebrow="Help" title="How can we help?" description="Find the next step for your document and understand what each result means." /><div className="grid gap-4 sm:grid-cols-2">{topics.map((topic) => <Panel key={topic.title} title={topic.title}><p className="min-h-24 text-sm leading-6 text-slate-600 dark:text-slate-300">{topic.body}</p><Link href={topic.href} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-teal-800 dark:text-teal-300">{topic.label} <ArrowUpRight size={15} aria-hidden="true" /></Link></Panel>)}</div></div>;
}
