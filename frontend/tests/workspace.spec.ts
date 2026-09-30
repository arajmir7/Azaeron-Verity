import { expect, test } from "@playwright/test";

test("public workspace keeps analysis evidence-based and editorial work authenticated", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Azaeron/);
  await expect(page.getByRole("heading", { level: 1, name: /Your words\. With clarity\./ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Five tools. A clearer way to work." })).toBeVisible();
  await expect(page.getByText(/WORKSPACE PREVIEW/)).toBeVisible();
  await expect(page.getByText(/Generative AI requires approved private models/)).toBeVisible();
  await expect(page.getByText(/\b\d{2,3}%/)).toHaveCount(0);
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/login/);
});

test("public navigation remains usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("link", { name: "Product" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create workspace" }).first()).toBeVisible();
});
