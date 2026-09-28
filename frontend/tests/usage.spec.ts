import { expect, test } from "@playwright/test";
import axe from "axe-core";

test("workspace usage shows authoritative totals and handles unavailable refresh", async ({ page }) => {
  const organization = { id: "usage-workspace", name: "Usage workspace", slug: "usage-workspace", subscription_tier: "free" };
  let unavailable = false;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "usage-user", email: "usage@example.com", is_active: true, onboarding_completed: true, product_role: "student", home_path: "/check", active_organization_id: organization.id, organizations: [{ organization_id: organization.id, role: "owner", is_active: true }] } });
    if (path.endsWith("/organizations")) return route.fulfill({ json: [organization] });
    if (path.endsWith("/select")) return route.fulfill({ json: organization });
    if (path.endsWith("/usage")) return unavailable
      ? route.fulfill({ status: 503, json: { detail: "Usage temporarily unavailable" } })
      : route.fulfill({ json: { period: "2026-09", unit: "operations", billing_enabled: false, limits: [{ task: "text_verify", committed: 17, reserved: 2, limit: 200 }] } });
    return route.fulfill({ status: 404, json: { detail: "Unexpected fixture request" } });
  });
  await page.goto("/settings?tab=workspace");
  await expect(page.getByText("17 completed · 2 pending · 200 limit")).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.addScriptTag({ content: axe.source });
  expect(await page.evaluate(async () => (window as unknown as { axe: typeof axe }).axe.run("section[aria-labelledby='usage-heading']").then((result) => result.violations))).toEqual([]);
  unavailable = true;
  await page.getByRole("button", { name: "Refresh usage" }).click();
  await expect(page.getByRole("region", { name: "Workspace usage" }).getByRole("alert")).toContainText("Usage temporarily unavailable");
});
