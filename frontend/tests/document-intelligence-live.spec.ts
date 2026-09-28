import { postWithRetryAfter } from "./live-request";
import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";

test.use({ video: "on", trace: "retain-on-failure" });

test("document core: upload, analyze and switch immutable versions across existing views", async ({ page, baseURL }, testInfo) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the migrated database, storage and worker stack");
  test.setTimeout(180_000);
  const headers = { Origin: baseURL! };
  const credentials = { email: `document-core-${Date.now()}@example.com`, password: "DocumentCore123!" };
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/login", { headers, data: credentials })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();

  const text1 = "Introduction\n\n🙂 First version: River basins support diverse habitats and require careful seasonal observations [1].\n\nReferences\n[1] Smith, J. (2020). Seasonal habitats.";
  const text2 = "Methods\n\nSecond version: Laboratory measurements show distinct sediment chemistry in mineral samples (Jones, 2022).\n\nReferences\nJones, A. (2022). Mineral measurements.";
  await page.goto("/check");
  const confirmation = page.waitForResponse((response) => response.url().endsWith("/documents/upload-confirm") && response.request().method() === "POST");
  await page.locator('input[type="file"]').setInputFiles({ name: "document-core.txt", mimeType: "text/plain", buffer: Buffer.from(text1) });
  const confirmed = await confirmation;
  expect(confirmed.ok()).toBeTruthy();
  const document = await confirmed.json();

  async function waitForVersion(versionId?: string) {
    await expect.poll(async () => {
      const response = await page.request.get(`/api/v1/detection/documents/${document.id}${versionId ? `?document_version_id=${versionId}` : ""}`);
      return response.status();
    }, { timeout: 60_000 }).toBe(200);
  }
  await waitForVersion();
  const content1 = await (await page.request.get(`/api/v1/documents/${document.id}/content`)).json();
  const v1 = content1.document_version_id as string;
  const structure1 = await (await page.request.get(`/api/v1/documents/${document.id}/structure?document_version_id=${v1}`)).json();
  expect(structure1.parser_version).toBe("document-structure-v1");
  expect(structure1.structure.references).toHaveLength(1);
  expect(structure1.structure.citations[0].text).toBe("[1]");
  expect(structure1.structure.citations[0].sentence_id).toBeTruthy();
  expect(structure1.structure_fingerprint).toMatch(/^[a-f0-9]{64}$/);

  async function evidence(versionId: string, expectedText: string) {
    const query = `?document_version_id=${versionId}`;
    const routes = [`/detection/documents/${document.id}`, `/citations/documents/${document.id}/analysis`,
      `/authorship/documents/${document.id}/analysis`, `/similarity/documents/${document.id}/analysis`,
      `/evidence/documents/${document.id}/graph`, `/reports/documents/${document.id}`];
    const result = [];
    for (const route of routes) {
      const response = await page.request.get(`/api/v1${route}${query}`);
      expect(response.ok(), await response.text()).toBeTruthy();
      const data = await response.json();
      expect(data.document_version_id).toBe(versionId);
      delete data.generated_at;
      result.push(data);
    }
    const graph = result[4];
    expect(graph.complete).toBeTruthy();
    for (const node of graph.nodes) {
      expect(node.document_version_id).toBe(versionId);
      if (node.span_text !== null) expect(Array.from(expectedText).slice(node.span_start, node.span_end).join("")).toBe(node.span_text);
    }
    for (const edge of graph.edges) expect(edge.document_version_id).toBe(versionId);
    for (const segment of result[0].segments) expect(segment.document_version_id).toBe(versionId);
    for (const collection of ["findings", "citations", "references", "sources"]) {
      for (const item of result[1][collection]) expect(item.document_version_id).toBe(versionId);
    }
    return result;
  }
  const originalEvidence = await evidence(v1, text1);
  await page.goto(`/documents/${document.id}?version=${v1}`);
  await expect(page.getByLabel("Document analysis version")).toHaveValue(v1);
  await expect(page.getByRole("region", { name: "Highlighted text" })).toContainText("First version:");
  await page.screenshot({ path: testInfo.outputPath("01-version-one.png"), fullPage: true });

  const revision = Buffer.from(text2);
  const slotResponse = await page.request.post("/api/v1/documents/upload-request", { headers, data: { filename: "revision.txt", content_type: "text/plain", file_size: revision.length } });
  expect(slotResponse.ok()).toBeTruthy();
  const slot = await slotResponse.json();
  expect((await page.request.put(slot.upload_url, { data: revision, headers: { "Content-Type": "text/plain" } })).ok()).toBeTruthy();
  const revisionResponse = await page.request.post(`/api/v1/documents/${document.id}/versions`, { headers, data: {
    upload_id: slot.upload_id, storage_key: slot.storage_key, sha256_fingerprint: createHash("sha256").update(revision).digest("hex"),
    change_summary: "Independent second version", edit_type: "revision",
  } });
  expect(revisionResponse.ok(), await revisionResponse.text()).toBeTruthy();
  const v2 = (await revisionResponse.json()).id as string;
  await waitForVersion(v2);
  const laterEvidence = await evidence(v2, text2);
  expect(laterEvidence[0].id).not.toBe(originalEvidence[0].id);
  const jobs = await (await page.request.get("/api/v1/jobs")).json();
  // Similarity v2 retains its own analysis job in addition to the upload worker
  // job. Check each workload separately so duplicate deliveries still fail.
  for (const jobType of ["document_processing", "similarity_analysis"]) {
    expect(jobs.items.filter((job: { document_id: string; job_type: string }) => job.document_id === document.id && job.job_type === jobType).map((job: { document_version_id: string }) => job.document_version_id).sort()).toEqual([v1, v2].sort());
  }

  await page.reload();
  await page.getByLabel("Document analysis version").selectOption(v2);
  await expect(page.getByLabel("Document analysis version")).toHaveValue(v2);
  await expect(page.getByRole("region", { name: "Highlighted text" })).toContainText("Second version:");
  await expect(page.getByRole("region", { name: "Highlighted text" })).not.toContainText("First version:");
  await page.getByRole("navigation", { name: "Document analysis navigation" }).getByRole("link", { name: "Citations", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`version=${v2}`));
  await expect(page.getByLabel("Module document version")).toHaveValue(v2);
  await page.getByLabel("Module document version").selectOption(v1);
  await expect(page.getByLabel("Module document version")).toHaveValue(v1);
  await page.getByRole("link", { name: "Report", exact: true }).click();
  await expect(page.getByLabel("Document analysis version")).toHaveValue(v1);
  await expect(page.getByRole("region", { name: "Highlighted text" })).toContainText("First version:");
  await expect(page.getByRole("region", { name: "Highlighted text" })).not.toContainText("Second version:");
  await page.getByRole("link", { name: "Review similarity", exact: true }).click();
  await expect(page.getByLabel("Similarity document version")).toHaveValue(v1);
  await page.getByRole("link", { name: "Graph", exact: true }).click();
  await expect(page.getByLabel("Module document version")).toHaveValue(v1);
  await page.screenshot({ path: testInfo.outputPath("02-historical-evidence-graph.png"), fullPage: true });
  expect(await evidence(v1, text1)).toEqual(originalEvidence);
  expect(await evidence(v2, text2)).toEqual(laterEvidence);
  expect(await (await page.request.get(`/api/v1/documents/${document.id}/structure?document_version_id=${v1}`)).json()).toEqual(structure1);

  await page.goto(`/documents/${document.id}?version=${v1}`);
  await expect(page.getByLabel("Document analysis version")).toHaveValue(v1);
  await page.getByRole("link", { name: "Improve with Write", exact: true }).click();
  await expect(page.getByLabel("Editor version history")).toHaveValue(v1);
  await expect(page.getByLabel("Draft text")).toHaveValue(text1);
  await page.goto(`/evidence-graph?document=${document.id}&version=${v1}`);
  await expect(page.getByLabel("Module document version")).toHaveValue(v1);

  const separate = await page.request.post("/api/v1/organizations", { headers, data: { name: "Isolated document core workspace" } });
  expect(separate.status()).toBe(201);
  const otherId = (await separate.json()).id;
  expect((await page.request.post(`/api/v1/organizations/${otherId}/select`, { headers })).ok()).toBeTruthy();
  expect((await page.request.get(`/api/v1/documents/${document.id}/structure?document_version_id=${v1}`)).status()).toBe(404);
  await page.reload();
  await expect(page.getByLabel("Module document version")).toHaveCount(0);
});
