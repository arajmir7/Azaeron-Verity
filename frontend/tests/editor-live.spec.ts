import { postWithRetryAfter } from "./live-request";
import { createHash, randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("editor: selective acceptance, reload, restore, offline recovery and lost-response retry", async ({ page, baseURL }) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the isolated database, storage and worker stack");
  test.setTimeout(120_000);
  const headers = { Origin: baseURL! };
  const credentials = { email: `editor-${Date.now()}@example.com`, password: "EditorWorkflow123!" };
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/login", { headers, data: credentials })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();
  const original = "In order to explain the finding, the the report  uses clear language.";
  const bytes = Buffer.from(original);
  const upload = await page.request.post("/api/v1/documents/upload-request", { headers, data: { filename: "editor.txt", content_type: "text/plain", file_size: bytes.length } });
  expect(upload.ok()).toBeTruthy();
  const slot = await upload.json();
  expect((await page.request.put(slot.upload_url, { data: bytes, headers: { "Content-Type": "text/plain" } })).ok()).toBeTruthy();
  const confirmation = await page.request.post("/api/v1/documents/upload-confirm", { headers, data: {
    upload_id: slot.upload_id, storage_key: slot.storage_key, original_filename: "editor.txt",
    sha256_fingerprint: createHash("sha256").update(bytes).digest("hex"),
  } });
  expect(confirmation.ok()).toBeTruthy();
  const doc = await confirmation.json();
  await expect.poll(async () => (await page.request.get(`/api/v1/documents/${doc.id}/content`)).status(), { timeout: 60_000 }).toBe(200);
  const initial = await (await page.request.get(`/api/v1/documents/${doc.id}/content`)).json();
  // A still-valid PUT URL addresses staging only, never accepted version bytes.
  expect((await page.request.put(slot.upload_url, { data: Buffer.from("Staging was overwritten."), headers: { "Content-Type": "text/plain" } })).ok()).toBeTruthy();
  const frozenDownload = await (await page.request.get(`/api/v1/documents/${doc.id}/download`)).json();
  expect(await (await page.request.get(frozenDownload.download_url)).text()).toBe(original);
  const replay = await page.request.post("/api/v1/documents/upload-confirm", { headers, data: {
    upload_id: slot.upload_id, storage_key: slot.storage_key, original_filename: "editor.txt",
    sha256_fingerprint: createHash("sha256").update(bytes).digest("hex"),
  } });
  expect((await replay.json()).id).toBe(doc.id);
  await page.goto(`/write?document=${doc.id}`);
  const draft = page.getByLabel("Draft text");
  await expect(draft).toHaveValue(original);
  await page.getByLabel("Editorial focus").selectOption("correctness");
  const refinements: string[] = [];
  await page.route("**/api/v1/aegiswrite/refine", async (route) => {
    expect(route.request().postDataJSON().edit_types).toEqual(["grammar", "structure"]);
    refinements.push(route.request().postDataJSON().operation_id);
    const committed = await route.fetch();
    expect(committed.ok()).toBeTruthy();
    await route.abort("failed");
  }, { times: 1 });
  await page.getByRole("button", { name: "Improve draft" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  page.on("request", (request) => {
    if (request.url().endsWith("/aegiswrite/refine")) refinements.push(request.postDataJSON().operation_id);
  });
  await page.getByRole("button", { name: "Improve draft" }).click();
  await expect(page.getByText("Original → revision → reason")).toBeVisible();
  expect(refinements).toHaveLength(2);
  expect(refinements[0]).toBe(refinements[1]);
  const usage = await (await page.request.get("/api/v1/usage")).json();
  expect(usage.limits.find((item: { task: string }) => item.task === "editorial").committed).toBe(1);
  await page.getByRole("checkbox").first().uncheck();
  const candidate = await page.getByLabel("Candidate text").innerText();
  expect(candidate).not.toBe(original);
  await page.getByRole("button", { name: "Accept selected changes" }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toHaveText("Saved version 2");
  await expect(draft).toHaveValue(candidate);
  await page.reload();
  await expect(draft).toHaveValue(candidate);
  expect((await (await page.request.get(`/api/v1/documents/${doc.id}/content?document_version_id=${initial.document_version_id}`)).json()).content).toBe(original);
  await page.getByLabel("Editor version history").selectOption(initial.document_version_id);
  await expect(draft).toHaveValue(original);
  await page.getByRole("button", { name: "Restore this version" }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toHaveText("Saved version 3");
  await expect(draft).toHaveValue(original);
  const download = await (await page.request.get(`/api/v1/documents/${doc.id}/download`)).json();
  expect(await (await page.request.get(download.download_url)).text()).toBe(original);

  const offlineDraft = `${original} Written while offline.`;
  await page.context().setOffline(true);
  await draft.fill(offlineDraft);
  await expect(page.getByRole("status", { name: "Editor status" })).toContainText("Offline");
  await page.context().setOffline(false);
  await page.reload();
  await expect(draft).toHaveValue(offlineDraft);
  const operations: string[] = [];
  await page.route(`**/api/v1/documents/${doc.id}/revisions`, async (route) => {
    operations.push(route.request().postDataJSON().operation_id);
    const committed = await route.fetch();
    expect(committed.ok()).toBeTruthy();
    await route.abort("failed"); // The server committed, but the client lost its response.
  }, { times: 1 });
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toContainText("Save failed");
  await expect(draft).toHaveValue(offlineDraft);
  await page.reload();
  await expect(draft).toHaveValue(offlineDraft);
  page.on("request", (request) => {
    if (request.url().endsWith(`/documents/${doc.id}/revisions`)) operations.push(request.postDataJSON().operation_id);
  });
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toHaveText("Saved version 4");
  expect(operations).toHaveLength(2);
  expect(operations[1]).toBe(operations[0]);

  // A concurrent writer must cause a visible conflict, preserving this tab's work.
  const fourth = await (await page.request.get(`/api/v1/documents/${doc.id}/content`)).json();
  await draft.fill("My local draft must survive a conflict.");
  const concurrent = await page.request.post(`/api/v1/documents/${doc.id}/revisions`, { headers, data: {
    operation_id: randomUUID(), base_version_id: fourth.document_version_id, text: "A concurrent accepted version.", edit_ids: [],
  } });
  expect(concurrent.ok(), await concurrent.text()).toBeTruthy();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toContainText("Conflict");
  await expect(draft).toHaveValue("My local draft must survive a conflict.");
  await page.reload();
  await expect(draft).toHaveValue("My local draft must survive a conflict.");
  expect((await (await page.request.get(`/api/v1/documents/${doc.id}/content`)).json()).content).toBe("A concurrent accepted version.");
});

test("editor: undo, redo, debounced autosave, rename and archive", async ({ page, baseURL }) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the isolated database, storage and worker stack");
  test.setTimeout(120_000);
  const headers = { Origin: baseURL! };
  const credentials = { email: `editor-autosave-${Date.now()}@example.com`, password: "EditorWorkflow123!" };
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/login", { headers, data: credentials })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();
  const original = "🙂 In order to explain the finding, we use data. In order to discuss it, we compare methods.";
  const bytes = Buffer.from(original);
  const upload = await page.request.post("/api/v1/documents/upload-request", { headers, data: { filename: "autosave.txt", content_type: "text/plain", file_size: bytes.length } });
  expect(upload.ok()).toBeTruthy();
  const slot = await upload.json();
  expect((await page.request.put(slot.upload_url, { data: bytes, headers: { "Content-Type": "text/plain" } })).ok()).toBeTruthy();
  const confirmed = await page.request.post("/api/v1/documents/upload-confirm", { headers, data: {
    upload_id: slot.upload_id, storage_key: slot.storage_key, original_filename: "autosave.txt",
    sha256_fingerprint: createHash("sha256").update(bytes).digest("hex"),
  } });
  expect(confirmed.ok()).toBeTruthy();
  const doc = await confirmed.json();
  await expect.poll(async () => (await page.request.get(`/api/v1/documents/${doc.id}/content`)).status(), { timeout: 60_000 }).toBe(200);
  await page.goto(`/write?document=${doc.id}`);
  const draft = page.getByLabel("Draft text");
  await expect(draft).toHaveValue(original);
  const revised = `${original} A second observation.`;
  await draft.fill(revised);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(draft).toHaveValue(original);
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(draft).toHaveValue(revised);
  await expect(page.getByRole("status", { name: "Editor status" })).toHaveText("Autosaved version 2", { timeout: 20_000 });
  const timeline = await (await page.request.get(`/api/v1/provenance/documents/${doc.id}/timeline`)).json();
  expect(timeline.versions).toHaveLength(2);
  await page.waitForTimeout(2200);
  expect((await (await page.request.get(`/api/v1/provenance/documents/${doc.id}/timeline`)).json()).versions).toHaveLength(2);
  // Autosave must not erase the user's undo history.
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(draft).toHaveValue(original);
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(draft).toHaveValue(revised);
  await page.getByLabel("Document title").fill("Renamed research draft");
  await page.getByRole("button", { name: "Rename" }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toHaveText("Document renamed");
  await page.reload();
  await expect(draft).toHaveValue(revised);
  await expect(page.getByLabel("Document title")).toHaveValue("Renamed research draft");
  // Textarea offsets are UTF-16; the API expects Unicode code points.
  await draft.evaluate((element: HTMLTextAreaElement) => { element.focus(); element.setSelectionRange(3, 13); });
  await draft.press("Shift+ArrowRight");
  await page.getByRole("button", { name: "Shorten", exact: true }).click();
  await expect(page.getByRole("status", { name: "Editor status" })).toHaveText("Selection ready for review");
  await expect(page.getByLabel("Candidate text")).toHaveText(revised.replace("In order to", "To"));
  await expect(page.getByLabel("Candidate text")).toContainText("In order to discuss");
  await page.getByRole("button", { name: "Reject candidate" }).click();
  await expect(draft).toHaveValue(revised);
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Archive document" }).click();
  await expect(page.getByText("Start with a document")).toBeVisible();
  expect((await (await page.request.get(`/api/v1/documents/${doc.id}`)).json()).status).toBe("archived");
  await page.reload();
  await expect(page.getByText("Start with a document")).toBeVisible();
});
