import { expect, test, type Response } from "@playwright/test";

test.use({ video: "on", trace: "retain-on-failure", actionTimeout: 15_000 });

test("live signup, personal workspace, upload, refresh and persistent switching", async ({ page, baseURL }, testInfo) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the migrated PostgreSQL, MinIO and worker stack");
  test.setTimeout(240_000);
  const email = `slice0-${Date.now()}@example.com`;
  const headers = { Origin: baseURL! };
  const loginResponses: Response[] = [];
  page.on("response", (response) => {
    if (response.url().endsWith("/api/v1/auth/login")) loginResponses.push(response);
  });
  async function honorRetryAfter(response: Response) {
    const seconds = Number(response.headers()["retry-after"]);
    expect(seconds).toBeGreaterThan(0);
    expect(seconds).toBeLessThanOrEqual(120);
    await page.waitForTimeout((seconds + 1) * 1000);
  }
  await page.goto("/register");
  await page.getByLabel("First name").fill("Slice Zero");
  await page.getByLabel("Last name").fill("Student");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel(/^Password/).fill("RecordedWorkspace123!");
  await page.getByLabel("Confirm password").fill("RecordedWorkspace123!");
  let registered = false;
  for (let attempt = 0; attempt < 3; attempt++) {
    const responsePromise = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/register"));
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    const response = await responsePromise;
    if (response.status() === 201) { registered = true; break; }
    expect(response.status()).toBe(429);
    await honorRetryAfter(response);
  }
  expect(registered).toBeTruthy();
  await expect.poll(() => loginResponses.length).toBeGreaterThan(0);
  if (loginResponses.at(-1)?.status() === 429) {
    await honorRetryAfter(loginResponses.at(-1)!);
    await page.goto("/login");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("RecordedWorkspace123!");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  }
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole("heading", { name: "How will you use Azaeron?" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("01-role-choice.png"), fullPage: true });
  await page.getByRole("radio", { name: /^Student / }).check();
  await page.getByRole("button", { name: "Create my personal workspace" }).click();
  await expect(page.getByRole("heading", { name: "Your personal workspace is ready." })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("02-personal-workspace.png"), fullPage: true });
  await page.getByRole("button", { name: "Continue to my first document" }).click();
  await expect(page).toHaveURL(/\/check$/);
  await expect(page.getByRole("heading", { name: "Check a document" })).toBeVisible();
  const initial = await (await page.request.get("/api/v1/auth/me")).json();
  const personalId = initial.active_organization_id;
  expect(personalId).toBeTruthy();
  expect(initial.organizations).toHaveLength(1);
  // Retry the first-run operation concurrently against real PostgreSQL.
  const retries = await Promise.all([1, 2].map(() => page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "student" } })));
  for (const response of retries) { expect(response.status()).toBe(200); expect((await response.json()).active_organization_id).toBe(personalId); }
  expect((await (await page.request.get("/api/v1/organizations")).json())).toHaveLength(1);
  const pastedTitle = `Pasted field notes ${Date.now()}`;
  const pastedText = "The field notes describe twelve seedlings observed in April. I recorded the planting date, counted surviving plants each week, and compared growth under two watering schedules. These observations are limited to one small garden and require replication before broader conclusions.";
  await page.getByRole("textbox", { name: "Document title" }).fill(pastedTitle);
  await page.getByRole("textbox", { name: "Your text" }).fill(pastedText);
  await expect(page.getByText("40 words", { exact: false })).toBeVisible();
  const pastedConfirmation = page.waitForResponse((response) => response.url().endsWith("/api/v1/documents/upload-confirm") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Create document" }).click();
  const pastedResponse = await pastedConfirmation;
  expect(pastedResponse.status()).toBe(200);
  const pastedDocument = await pastedResponse.json();
  await expect(page).toHaveURL(new RegExp(`/documents/${pastedDocument.id}$`));
  await expect.poll(async () => (await (await page.request.get(`/api/v1/documents/${pastedDocument.id}`)).json()).status, { timeout: 60_000 }).toBe("completed");
  const pastedContent = await (await page.request.get(`/api/v1/documents/${pastedDocument.id}/content`)).json();
  expect(pastedContent.content).toBe(pastedText);
  await page.goto("/check");
  await page.getByRole("button", { name: "Upload file" }).click();
  const documentName = `first-paper-${Date.now()}.txt`;
  const confirmed = page.waitForResponse((response) => response.url().endsWith("/api/v1/documents/upload-confirm") && response.request().method() === "POST");
  await page.locator('input[type="file"]').setInputFiles({
    name: documentName, mimeType: "text/plain",
    buffer: Buffer.from("My first paper records how a garden changed through the seasons. I counted twelve seedlings in April and noted which plants survived. These observations describe my own small experiment. The sample is limited, so I do not draw broader conclusions from it."),
  });
  const confirmation = await confirmed;
  expect(confirmation.status()).toBe(200);
  const document = await confirmation.json();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.getByText(documentName).first()).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/documents/${document.id}`)).json()).status, { timeout: 60_000 }).toBe("completed");
  await page.goto(`/documents/${document.id}`);
  await expect(page.getByText(documentName).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("03-first-document.png"), fullPage: true });
  const second = await page.request.post("/api/v1/organizations", { headers, data: { name: "Recorded research team" } });
  expect(second.status()).toBe(201);
  const secondId = (await second.json()).id;
  await page.goto("/documents");
  await page.reload();
  await page.getByRole("combobox", { name: "Active workspace" }).selectOption(secondId);
  await expect(page.getByText("Your library is empty")).toBeVisible();
  expect((await page.request.get(`/api/v1/documents/${document.id}`)).status()).toBe(404);
  const refreshed = await page.request.post("/api/v1/auth/refresh", { headers, data: {} });
  expect(refreshed.status()).toBe(200);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(secondId);
  await page.getByRole("combobox", { name: "Active workspace" }).selectOption(personalId);
  await expect(page.getByText(documentName).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("04-restored-workspace.png"), fullPage: true });
});
