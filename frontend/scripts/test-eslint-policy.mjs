import assert from "node:assert/strict";
import { ESLint } from "eslint";

const eslint = new ESLint();
const cases = [
  ["async client component", '"use client"; export default async function Page() { return <div/>; }', "verity-next/no-async-client-component"],
  ["raw head", "export default function Page() { return <head/>; }", "verity-next/app-router-elements"],
  ["unoptimized image", 'export default function Page() { return <img alt="x"/>; }', "verity-next/app-router-elements"],
  ["raw script", 'export default function Page() { return <script src="/x.js"/>; }', "verity-next/app-router-elements"],
  ["internal anchor", 'export default function Page() { return <a href="/docs">Docs</a>; }', "verity-next/app-router-elements"],
  ["missing React list key", "export default function Page() { return [<span/>, <span/>]; }", "react/jsx-key"],
  ["missing image alternative", 'export default function Page() { return <img src="/x"/>; }', "jsx-a11y/alt-text"],
];

for (const [label, source, requiredRule] of cases) {
  const [result] = await eslint.lintText(source, { filePath: "src/lint-policy-probe.tsx" });
  assert(result.messages.some((message) => message.ruleId === requiredRule), `${label}: ${requiredRule} was not enforced`);
}
console.log(`ESLint policy: ${cases.length} boundary checks passed`);
