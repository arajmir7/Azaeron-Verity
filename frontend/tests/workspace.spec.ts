import { expect, test } from "@playwright/test";

test("public workspace keeps analysis evidence-based and editorial work authenticated", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Azaeron/);
  await expect(page.getByRole("heading", { name: /Make every decision defensible/ })).toBeVisible();
  await expect(page.getByText("NO SAMPLE DATA")).toBeVisible();
  await expect(page.getByText("No fabricated metrics")).toBeVisible();
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
