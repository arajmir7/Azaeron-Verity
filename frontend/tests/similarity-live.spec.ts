import { postWithRetryAfter } from "./live-request";
import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { SimilarityWorkflow } from "../src/lib/api";

test.use({ video: "on", trace: "retain-on-failure" });

test("similarity: real corpus, evidence, exclusions, pagination and immutable versions", async ({ page, baseURL }, testInfo) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires migrated PostgreSQL, MinIO and Celery");
  test.setTimeout(180_000);
  const headers = { Origin: baseURL! };
  const unique = Date.now();
  const register = await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: { email: `similarity-${unique}@example.com`, password: "SimilarityEvidence123!", first_name: "Similarity", last_name: "Reviewer" } });
  expect(register.status()).toBe(201);
  const login = await postWithRetryAfter(page.request, "/api/v1/auth/login", { headers, data: { email: `similarity-${unique}@example.com`, password: "SimilarityEvidence123!" } });
  expect(login.status()).toBe(200);
  const onboarding = await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "student" } });
  expect(onboarding.status()).toBe(200);

  async function upload(text: string, filename: string, parent?: string) {
    const content = Buffer.from(text);
    const slot = await page.request.post("/api/v1/documents/upload-request", { headers, data: { filename, content_type: "text/plain", file_size: content.length } });
    expect(slot.ok()).toBeTruthy();
    const { upload_url, upload_id, storage_key } = await slot.json();
    expect((await page.request.put(upload_url, { data: content, headers: { "Content-Type": "text/plain" } })).ok()).toBeTruthy();
    const result = await page.request.post(parent ? `/api/v1/documents/${parent}/versions` : "/api/v1/documents/upload-confirm", {
      headers, data: { upload_id, storage_key, sha256_fingerprint: createHash("sha256").update(content).digest("hex"), ...(parent ? { change_summary: "Independent second version", edit_type: "revision" } : { original_filename: filename }) },
    });
    expect(result.ok(), await result.text()).toBeTruthy();
    const record = await result.json();
    const id = parent || record.id;
    await expect.poll(async () => {
      const query = parent ? `?document_version_id=${record.id}` : "";
      const response = await page.request.get(`/api/v1/similarity/documents/${id}/analysis${query}`);
      return response.ok() ? (await response.json()).analysis_state : "PENDING";
    }, { timeout: 60_000 }).toMatch(/READY|BOUNDED/);
    return record;
  }
  const phrases = [
    "River basins support diverse habitats and seasonal migration patterns across connected ecosystems",
    "Controlled laboratory measurements require calibrated instruments and detailed records for independent replication",
    "Long term rainfall observations reveal seasonal variation across mountainous agricultural catchments",
    "Transparent reporting separates observed results from interpretations and acknowledges the limits of each sample",
  ];
  const sourceText = phrases.join(".\n\n") + ".";
  const sourceOne = await upload(sourceText + "\nFirst workspace source record.", "source-one.txt");
  await upload(sourceText + "\nSecond workspace source record.", "source-two.txt");
  const targetText = `Passage A: ${phrases[0]}.\n\nPassage B: “${phrases[1]}” (Reed, 2021).\n\nPassage C: ${phrases[2]} (Patel, 2022).\n\nPassage D: “${phrases[3]}.”\n\nReferences\nReed, J. (2021). Laboratory records.\nPatel, A. (2022). Rainfall observations.`;
  await page.goto("/check");
  const confirmed = page.waitForResponse((response) => response.url().endsWith("/documents/upload-confirm") && response.request().method() === "POST");
  await page.locator('input[type="file"]').setInputFiles({ name: "similarity-paper.txt", mimeType: "text/plain", buffer: Buffer.from(targetText) });
  const confirmation = await confirmed;
  expect(confirmation.ok()).toBeTruthy();
  const target = await confirmation.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/documents/${target.id}`)).json()).status, { timeout: 60_000 }).toBe("completed");
  await page.goto(`/documents/${target.id}`);
  await page.getByRole("link", { name: "Review similarity" }).click();
  await expect(page.getByRole("heading", { name: "Review matching text", exact: true })).toBeVisible();
  await expect(page.getByTestId("similarity-percentage")).not.toHaveText("Unavailable");
  await expect(page.getByText("PRIVATE_WORKSPACE", { exact: true })).toBeVisible();
  await expect(page.getByText("PUBLIC_METADATA", { exact: true })).toBeVisible();
  const original: SimilarityWorkflow = await (await page.request.get(`/api/v1/similarity/documents/${target.id}/analysis`)).json();
  expect(original.summary.percentage).toBeGreaterThan(0);
  expect(original.summary.percentage).toBeLessThanOrEqual(100);
  expect(original.sources.total).toBe(2);
  expect(original.groups.every((group) => group.matches > 0)).toBeTruthy();
  expect(original.sources.items.reduce((sum, source) => sum + source.matched_words, 0)).toBeGreaterThan(original.summary.matched_words);
  await page.getByRole("button", { name: /^Inspect match/ }).first().click();
  const selected = original.matches.items[0];
  await expect(page.getByRole("region", { name: "Target evidence" }).locator("mark")).toHaveText(selected.matched_text);
  await expect(page.getByRole("region", { name: "Source evidence" }).locator("mark")).toHaveText(selected.source_text);
  const targetContent = await (await page.request.get(`/api/v1/documents/${target.id}/content?document_version_id=${original.document_version_id}`)).json();
  const sourceContent = await (await page.request.get(`/api/v1/documents/${selected.source_document_id}/content?document_version_id=${selected.source_document_version_id}`)).json();
  // Python offsets count Unicode code points; avoid JavaScript UTF-16 slicing.
  expect(Array.from(targetContent.content as string).slice(selected.document_span_start, selected.document_span_end).join("")).toBe(selected.matched_text);
  expect(Array.from(sourceContent.content as string).slice(selected.source_span_start, selected.source_span_end).join("")).toBe(selected.source_text);
  expect(selected.source_content_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(selected.evidence_node_id).toBeTruthy();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("01-similarity-evidence.png"), fullPage: true });
  const excludedResponse = page.waitForResponse((response) => response.url().includes("/similarity/") && response.url().includes("exclude_quotes=true") && response.request().method() === "GET");
  await page.getByLabel("Exclude quoted text", { exact: true }).check();
  const excluded: SimilarityWorkflow = await (await excludedResponse).json();
  expect(excluded.summary.matched_words).toBeLessThan(original.summary.matched_words);
  expect(excluded.exclusions_hash).not.toBe(original.exclusions_hash);
  await page.reload();
  await expect(page.getByLabel("Exclude quoted text", { exact: true })).toBeChecked();
  await expect(page.getByTestId("similarity-percentage")).toHaveText(`${excluded.summary.percentage!.toFixed(2)}%`);
  await page.goto(`/similarity?document=${target.id}&version=${original.document_version_id}&page_size=1&source_page_size=1`);
  await page.getByRole("button", { name: "Next matches page" }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("button", { name: "Previous matches page" })).toBeEnabled();
  await page.getByRole("button", { name: "Next sources page" }).click();
  await expect(page).toHaveURL(/source_page=2/);
  await expect(page.getByRole("button", { name: "Previous sources page" })).toBeEnabled();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("02-similarity-pagination.png"), fullPage: true });
  const v2 = await upload("This independent revision discusses sediment chemistry and soil measurements from an unrelated field survey. Each observation has a different focus.", "revision.txt", target.id);
  await page.reload();
  await page.getByLabel("Similarity document version").selectOption(v2.id);
  await expect(page.getByTestId("similarity-percentage")).toHaveText("0.00%");
  await page.getByLabel("Similarity document version").selectOption(original.document_version_id);
  await expect(page.getByTestId("similarity-percentage")).toHaveText(`${original.summary.percentage!.toFixed(2)}%`);
  const prior = await (await page.request.get(`/api/v1/similarity/documents/${target.id}/analysis?document_version_id=${original.document_version_id}`)).json();
  expect(prior.analysis_id).toBe(original.analysis_id);
  expect(prior.matches.items.map((item: { id: string }) => item.id)).toEqual(original.matches.items.map((item) => item.id));
  const other = await page.request.post("/api/v1/organizations", { headers, data: { name: "Separate similarity workspace" } });
  expect(other.status()).toBe(201);
  const otherId = (await other.json()).id;
  expect((await page.request.post(`/api/v1/organizations/${otherId}/select`, { headers })).ok()).toBeTruthy();
  expect((await page.request.get(`/api/v1/similarity/documents/${target.id}/analysis`)).status()).toBe(404);
  expect((await page.request.get(`/api/v1/similarity/documents/${sourceOne.id}/analysis`)).status()).toBe(404);
  await page.reload();
  await expect(page.getByTestId("similarity-percentage")).toHaveCount(0);
});
