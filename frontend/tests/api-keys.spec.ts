import { expect, test } from "@playwright/test";
import axe from "axe-core";

test("API keys show the secret once, rotate, revoke, and avoid browser storage", async ({ page }) => {
  const organization = { id: "key-workspace", name: "Key workspace", slug: "key-workspace", subscription_tier: "free" };
  const secret = ["fixture", "display", "once"].join("-");
  let key: Record<string, unknown> | undefined;
  let created = 0;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/sessions")) return route.fulfill({ json: [] });
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "key-user", email: "keys@example.com", is_active: true, is_verified: true, onboarding_completed: true, product_role: "student", home_path: "/check", active_organization_id: organization.id, organizations: [{ organization_id: organization.id, role: "owner", is_active: true }] } });
    if (path.endsWith("/organizations")) return route.fulfill({ json: [organization] });
    if (path.endsWith("/select")) return route.fulfill({ json: organization });
    if (path.endsWith("/api-keys") && request.method() === "GET") return route.fulfill({ json: key ? [key] : [] });
    if (path.endsWith("/api-keys") && request.method() === "POST") {
      created++;
      const input = request.postDataJSON();
      expect(input.scopes).toEqual(["documents:read", "text:verify"]);
      key = { ...input, id: "key-id", key_prefix: "avk_test", is_active: true, last_used_at: null, created_at: new Date().toISOString() };
      return route.fulfill({ status: 201, json: { key, secret } });
    }
    if (path.endsWith("/rotate")) return route.fulfill({ status: 201, json: { key, secret: secret + "-rotated" } });
    if (path.endsWith("/api-keys/key-id") && request.method() === "DELETE") {
      key = { ...key, is_active: false };
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
  });
  await page.goto("/settings?tab=security");
  await page.getByLabel("Key name", { exact: true }).fill("Review pipeline");
  await page.getByLabel("text:verify", { exact: true }).check();
  await page.getByRole("button", { name: "Create API key", exact: true }).click();
  const value = page.getByLabel("New API key — shown once");
  await expect(value).toHaveValue(secret);
  await expect(value).toBeFocused();
  expect(created).toBe(1);
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(secret);
  await page.getByRole("button", { name: "I saved the secret" }).click();
  await expect(value).toHaveCount(0);
  await page.reload();
  await expect(value).toHaveCount(0);
  await page.getByRole("button", { name: "Rotate Review pipeline" }).click();
  await expect(value).toHaveValue(secret + "-rotated");
  await page.getByRole("button", { name: "I saved the secret" }).click();
  await page.getByRole("button", { name: "Revoke Review pipeline" }).click();
  await expect(page.getByRole("button", { name: "Revoke Review pipeline" })).toHaveCount(0);
  await expect(page.getByText("API key revoked.", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.addScriptTag({ content: axe.source });
  const accessibility = await page.evaluate(async () => (window as unknown as { axe: typeof axe }).axe.run("section[aria-labelledby='api-keys-heading']"));
  expect(accessibility.violations).toEqual([]);
});
