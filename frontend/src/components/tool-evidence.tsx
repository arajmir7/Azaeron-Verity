"use client";

export function ToolEvidence({ content }: { content: Record<string, unknown> }) {
  const text = [content.text, content.summary, content.label, content.candidate, content.diff].filter((value): value is string => typeof value === "string");
  const limits = [content.limitation, ...(Array.isArray(content.limitations) ? content.limitations : [])].filter((value): value is string => typeof value === "string");
  const items = Array.isArray(content.items) ? content.items : undefined;
  return <div className="mt-3 space-y-3 text-sm leading-6">
    {text.map((value, index) => <p key={index} className="whitespace-pre-wrap break-words">{value}</p>)}
    {content.confirmation_required === true && <p>Review the candidate and its Verity Receipt below before accepting a new version.</p>}
    {items && <p>{items.length} matching document{items.length === 1 ? "" : "s"} in your workspace.</p>}
    {items?.map((item, index) => <p key={index}>{typeof item === "object" && item !== null && "title" in item ? String(item.title) : "Recorded source"}</p>)}
    {limits.map((value, index) => <p key={index} className="text-xs text-slate-500">{value}</p>)}
    {!text.length && !items && !content.confirmation_required && <p>{content.code ? "This action could not finish. See the recorded reason below." : "Evidence recorded for the attached version. Expand the details to review sources and findings."}</p>}
    <details><summary className="cursor-pointer text-xs font-medium">Recorded evidence</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(content, null, 2)}</pre></details>
  </div>;
}
