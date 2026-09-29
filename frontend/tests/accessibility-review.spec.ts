import { writeFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import axe from "axe-core";
import { postWithRetryAfter } from "./live-request";

async function wcagViolations(page: import("@playwright/test").Page) {
  await page.addScriptTag({ content: axe.source });
  return page.evaluate(async () => {
    const engine = (window as unknown as { axe: typeof axe }).axe;
    const result = await engine.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] } });
    return { violations: result.violations.map(({ id, nodes }) => ({ id, targets: nodes.map(({ target }) => target) })), incomplete: result.incomplete.map(({ id, nodes }) => ({ id, targets: nodes.map(({ target }) => target) })) };
  });
}

test("critical navigation stays operable at narrow widths and restores focus", async ({ page, baseURL }, testInfo) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the isolated migrated runtime");
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 320, height: 900 });
  for (const route of ["/login", "/register"]) {
    await page.goto(route);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    expect((await wcagViolations(page)).violations, route).toEqual([]);
  }
  await page.goto("/login");
  await page.screenshot({ path: testInfo.outputPath("mobile-login.png"), fullPage: true });
  const headers = { Origin: baseURL! };
  const credentials = {
    email: `a11y-review-${Date.now()}@example.com`,
    password: "AccessibleReview123!",
  };
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/login", { headers, data: credentials })).status()).toBe(200);
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();

  const review = [];
  for (const width of [1280, 640, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["/dashboard", "/ai", "/humaniser", "/detector", "/plagiarism", "/write", "/history", "/settings?tab=security", "/documents"]) {
      await page.goto(route);
      await expect(page.getByRole("main")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      if (route.includes("security")) {
        await expect(page.getByRole("heading", { name: "Workspace API keys" })).toBeVisible();
        await expect(page.getByRole("textbox", { name: "Key name" })).toBeVisible();
      }
      const dimensions = await page.evaluate(() => ({
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
        main: document.querySelector("main")?.getBoundingClientRect().width,
      }));
      review.push({ width, route, ...dimensions });
      expect(dimensions.document, `${route} at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
      if (width === 320) {
        const scan = await wcagViolations(page);
        review.push({ width, route, accessibility: scan });
        expect(scan.violations, route).toEqual([]);
      }
    }
  }

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/dashboard");
  const opener = page.getByRole("button", { name: "Open navigation" });
  await expect(opener).toBeVisible();
  await expect(page.getByRole("link", { name: "Dashboard", exact: true })).toHaveCount(0);
  await opener.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Primary navigation" });
  await expect(drawer).toBeVisible();
  await expect.poll(async () => {
    const box = await drawer.boundingBox();
    return box ? box.x >= 0 && box.x + box.width <= 376 : false;
  }).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("mobile-navigation-open.png"), fullPage: true });
  await expect(drawer.getByRole("button", { name: "Close navigation" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(drawer.getByRole("link", { name: "AZAERON dashboard" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(drawer.getByRole("button", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(drawer.getByRole("link", { name: "AZAERON dashboard" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(opener).toBeFocused();

  await page.emulateMedia({ reducedMotion: "reduce" });
  const reduced = await page.evaluate(() => {
    const element = document.querySelector("aside[aria-label='Primary navigation']");
    return element ? getComputedStyle(element).transitionDuration : null;
  });
  review.push({ reduced_motion_navigation_transition: reduced });
  expect(Number.parseFloat(reduced || "1")).toBeLessThanOrEqual(0.00001);
  await writeFile(testInfo.outputPath("structured-review.json"), JSON.stringify(review, null, 2) + "\n");
  await testInfo.attach("structured-review", { body: JSON.stringify(review, null, 2), contentType: "application/json" });
  await page.screenshot({ path: testInfo.outputPath("mobile-navigation-closed.png"), fullPage: true });
});
