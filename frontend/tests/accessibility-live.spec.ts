import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import axe from "axe-core";
import { postWithRetryAfter } from "./live-request";

async function tabTo(page: Page, selector: string) {
  for (let index = 0; index < 40; index += 1) {
    await page.keyboard.press("Tab");
    if (await page.evaluate((target) => document.activeElement?.matches(target), selector)) return;
  }
  throw new Error(`Control is not reachable by keyboard: ${selector}`);
}

test("keyboard login and refinement; critical pages have no automated WCAG AA violations", async ({ page, baseURL }, testInfo) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the isolated migrated runtime");
  test.setTimeout(240_000);
  const headers = { Origin: baseURL! };
  const credentials = { email: `accessibility-${Date.now()}@example.com`, password: "AccessibleDraft123!" };
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);

  await page.goto("/login");
  await tabTo(page, 'input[type="email"]');
  await page.keyboard.type(credentials.email);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.type(credentials.password);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeFocused();
  for (let attempt = 0; ; attempt++) {
    const pending = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST");
    await page.keyboard.press("Enter");
    const response = await pending;
    if (response.status() !== 429 || attempt >= 2) { expect(response.status()).toBe(200); break; }
    const retry = Number(response.headers()["retry-after"]);
    expect(retry).toBeGreaterThan(0);
    expect(retry).toBeLessThanOrEqual(60);
    await page.waitForTimeout((retry + 1) * 1000);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeFocused();
  }
  await expect(page).toHaveURL(/onboarding/);
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();

  const source = Buffer.from("In order to explain the finding, the the report uses clear language.");
  const slotResponse = await page.request.post("/api/v1/documents/upload-request", {
    headers, data: { filename: "accessible.txt", content_type: "text/plain", file_size: source.length },
  });
  expect(slotResponse.ok()).toBeTruthy();
  const slot = await slotResponse.json();
  expect((await page.request.put(slot.upload_url, { data: source, headers: { "Content-Type": "text/plain" } })).ok()).toBeTruthy();
  const confirmation = await page.request.post("/api/v1/documents/upload-confirm", { headers, data: {
    upload_id: slot.upload_id, storage_key: slot.storage_key, original_filename: "accessible.txt",
    sha256_fingerprint: createHash("sha256").update(source).digest("hex"),
  } });
  expect(confirmation.ok()).toBeTruthy();
  const document = await confirmation.json();
  await expect.poll(async () => (await page.request.get(`/api/v1/documents/${document.id}/content`)).status(), { timeout: 60_000 }).toBe(200);

  const reports = [];
  for (const route of ["/check", "/documents", `/write?document=${document.id}`]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (route.startsWith("/write")) {
      await tabTo(page, 'textarea[aria-label="Draft text"]');
      await page.keyboard.press("ControlOrMeta+A");
      await page.keyboard.type(source.toString());
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "Improve draft" })).toBeFocused();
      await expect(page.getByRole("button", { name: "Improve draft" })).toBeEnabled();
      await page.keyboard.press("Enter");
      await expect(page.getByText("Original → revision → reason")).toBeVisible();
    }
    await page.addScriptTag({ content: axe.source });
    const report = await page.evaluate(async () => {
      const engine = (window as unknown as { axe: typeof axe }).axe;
      return engine.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] } });
    });
    reports.push({ route, violations: report.violations, incomplete: report.incomplete });
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await page.setViewportSize({ width: 1280, height: 720 });
  }
  await testInfo.attach("accessibility-report", { body: JSON.stringify(reports, null, 2), contentType: "application/json" });
  await page.screenshot({ path: testInfo.outputPath("keyboard-refinement.png"), fullPage: true });
  expect(reports.flatMap((report) => report.violations.map((violation) => ({ route: report.route, id: violation.id, nodes: violation.nodes.map((node) => node.target) })))).toEqual([]);
});
