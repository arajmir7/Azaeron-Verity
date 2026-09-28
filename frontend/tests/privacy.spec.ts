import { expect, test } from "@playwright/test";
import axe from "axe-core";

test("privacy form requires explicit confirmation and keeps its receipt out of persistent storage", async ({ page }) => {
  const organization = { id: "privacy-org", name: "Privacy workspace", slug: "privacy-org", role: "owner", subscription_tier: "free" };
  const id = "ae6e6809-9c80-46a7-9776-4ad92f5c3f95";
  const receipt = "fixture-receipt-" + "r".repeat(32);
  let posted = 0;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "privacy-user", email: "privacy@example.com", is_active: true, is_verified: true, mfa_enabled: false, onboarding_completed: true, product_role: "student", active_organization_id: organization.id, organizations: [{ organization_id: organization.id, role: "owner", is_active: true }] } });
    if (path.endsWith("/organizations")) return route.fulfill({ json: [organization] });
    if (path.endsWith("/select")) return route.fulfill({ json: organization });
    if (path.endsWith("/auth/sessions") || path.endsWith("/api-keys")) return route.fulfill({ json: [] });
    if (path.endsWith("/privacy/erasures") && request.method() === "POST") {
      posted++;
      expect(request.postDataJSON()).toEqual({ scope: "account", target_id: "privacy-user", current_password: "fixture-password-only", confirmation: "ERASE" });
      return route.fulfill({ status: 202, json: { id, status: "REQUESTED", receipt, message: "Queued" } });
    }
    if (path.endsWith(`/privacy/erasures/${id}`)) {
      expect(request.headers()["x-erasure-receipt"]).toBe(receipt);
      return route.fulfill({ json: { id, scope: "account", status: "VERIFYING", created_at: new Date().toISOString(), completed_at: null, last_error: null } });
    }
    return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
  });
  await page.goto("/settings?tab=security");
  await page.getByLabel("Data to erase").selectOption("account");
  await page.getByLabel("Password to authorize erasure").fill("fixture-password-only");
  const submit = page.getByRole("button", { name: "Permanently erase selected data" });
  await expect(submit).toBeDisabled();
  await page.getByLabel("Type ERASE to confirm").fill("ERASE");
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addScriptTag({ content: axe.source });
  expect(await page.evaluate(async () => (window as unknown as { axe: typeof axe }).axe.run("section[aria-labelledby='privacy-heading']").then((result) => result.violations))).toEqual([]);
  await submit.click();
  await expect(page).toHaveURL(/\/erasure-status$/);
  await expect(page.getByLabel("Erasure receipt", { exact: true })).toHaveValue(receipt);
  expect(posted).toBe(1);
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(receipt);
  await page.getByRole("button", { name: "Check erasure status" }).click();
  await expect(page.getByRole("status")).toContainText("in progress");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.addScriptTag({ content: axe.source });
  expect(await page.evaluate(async () => (window as unknown as { axe: typeof axe }).axe.run().then((result) => result.violations))).toEqual([]);
  await page.reload();
  await expect(page.getByLabel("Erasure receipt", { exact: true })).toHaveValue("");
});
