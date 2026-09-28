import { randomUUID } from "node:crypto";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { postWithRetryAfter } from "./live-request";

test("browser upload correlates API, database, storage and worker without customer text", async ({ page, request, baseURL }) => {
  test.skip(process.env.RUN_OBSERVABILITY_E2E !== "1", "Requires isolated self-hosted telemetry");
  test.setTimeout(180_000);
  const headers = { Origin: baseURL! };
  const credentials = { email: `telemetry-${randomUUID()}@example.com`, password: `Telemetry-${randomUUID()}!` };
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/login", { headers, data: credentials })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();
  const canary = `PRIVATE-CUSTOMER-CANARY-${randomUUID()}`;
  await page.goto("/check");
  const confirmation = page.waitForResponse(r => r.url().endsWith("/documents/upload-confirm") && r.request().method() === "POST");
  await page.locator('input[type="file"]').setInputFiles({ name: "telemetry-fixture.txt", mimeType: "text/plain", buffer: Buffer.from(`The protected marker ${canary} must never enter operational telemetry. A second sentence supports a realistic analysis.`) });
  const confirmed = await confirmation;
  expect(confirmed.ok()).toBeTruthy();
  const traceId = confirmed.headers()["x-trace-id"];
  const requestId = confirmed.headers()["x-request-id"];
  expect(traceId).toMatch(/^[a-f0-9]{32}$/);
  const document = await confirmed.json();
  await expect.poll(async () => (await page.request.get(`/api/v1/documents/${document.id}/content`)).status(), { timeout: 60_000 }).toBe(200);
  const jaeger = process.env.JAEGER_URL || "http://localhost:18386";
  type Tag = { key: string; value: string | number };
  type Span = { operationName: string; spanID: string; references: { spanID: string; refType: string }[]; tags: Tag[]; processID: string };
  let spans: Span[] = [];
  let raw = "";
  await expect.poll(async () => {
    const response = await request.get(`${jaeger}/api/traces/${traceId}`);
    if (!response.ok()) return false;
    raw = await response.text();
    spans = JSON.parse(raw).data?.[0]?.spans || [];
    return spans.some(s => s.operationName === "POST /api/v1/documents/upload-confirm") &&
      spans.some(s => s.operationName === "celery.process_document") &&
      spans.some(s => s.operationName === "storage.GET");
  }, { timeout: 60_000 }).toBe(true);
  expect(raw).not.toContain(canary);
  expect(raw).not.toContain("db.statement");
  const api = spans.find(s => s.operationName === "POST /api/v1/documents/upload-confirm");
  expect(api, `Trace ${traceId} is missing the upload API span; operations: ${spans.map(s => s.operationName).join(", ")}`).toBeDefined();
  if (!api) throw new Error("Upload API span missing after trace assertion");
  expect(api.tags.some(t => t.key === "request.id" && t.value === requestId)).toBeTruthy();
  const consumer = spans.find(s => s.operationName === "celery.process_document" && s.tags.some(t => t.key === "request.id" && t.value === requestId))!;
  expect(consumer).toBeTruthy();
  expect(consumer.references.some(r => r.spanID === api.spanID)).toBeTruthy();
  expect(spans.filter(s => s.operationName.startsWith("db.")).length).toBeGreaterThan(0);
  expect(spans.some(s => s.tags.some(t => t.key === "job.id"))).toBeTruthy();
  expect(spans.some(s => s.tags.some(t => t.key === "operation.id"))).toBeTruthy();
  expect(raw).toContain("release.id");
  const report = page.waitForResponse(r => r.url().endsWith("/telemetry/browser"));
  await page.evaluate(marker => window.dispatchEvent(new ErrorEvent("error", { message: marker, error: new Error(marker) })), canary);
  const reported = await report;
  expect(reported.status()).toBe(202);
  const sent = reported.request().postDataJSON();
  expect(Object.keys(sent).sort()).toEqual(["event_id", "kind", "route"]);
  expect(JSON.stringify(sent)).not.toContain(canary);
  const prometheus = process.env.PROMETHEUS_URL || "http://localhost:10790";
  await expect.poll(async () => {
    const response = await request.get(`${prometheus}/api/v1/query`, { params: { query: 'sum(azaeron_job_duration_seconds_count{job="azaeron-worker"})' } });
    return Number((await response.json()).data.result[0]?.value[1] || 0);
  }, { timeout: 45_000 }).toBeGreaterThan(0);
  const directory = resolve(process.env.OBSERVABILITY_EVIDENCE || "../docs/verity/evidence/remediation/r9");
  await mkdir(directory, { recursive: true });
  await writeFile(resolve(directory, "browser-correlation.json"), JSON.stringify({
    result: "PASS", trace_id: traceId, request_id: requestId, canary,
    checks: ["browser upload", "API span", "DB child spans", "storage spans", "worker parent", "job/operation/release IDs", "closed browser error report", "scraped worker metrics", "no customer text in trace"],
    spans: spans.map(s => ({ name: s.operationName, id: s.spanID, parents: s.references })),
    model_runtime: "BLOCKED: approved model/hardware unavailable",
  }, null, 2) + "\n");
});
