import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("local MLX preview answers in the authenticated workspace without approval claims", async ({ page, baseURL }) => {
  test.skip(process.env.RUN_DEV_MLX_E2E !== "1", "Explicit localhost MLX stack only");
  test.setTimeout(120_000);
  const headers = { Origin: baseURL! };
  const credentials = { email: `mlx-${randomUUID()}@example.com`, password: randomUUID() + "Aa9!" };
  expect((await page.request.post("/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  expect((await page.request.post("/api/v1/auth/login", { headers, data: credentials })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "researcher" } })).ok()).toBeTruthy();
  await page.goto("/ai");
  await expect(page.getByText("Local preview · unverified", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Ask Azaeron AI" }).fill("What is 2+2? Reply with one digit.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByLabel("Conversation messages").getByText("4", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByText("Trust Drawer · recorded tools and model evidence", { exact: true }).click();
  await expect(page.getByText("independent_verifier_not_approved", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Conversation messages")).not.toContainText("<think>");
  await page.goto("/humaniser");
  await expect(page.getByText("Use Humanise with AI on a saved version", { exact: false })).toBeVisible();
});
