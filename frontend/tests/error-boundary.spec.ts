import { expect, test } from "@playwright/test";

test("render errors have a focused recovery boundary and send only closed metadata", async ({ page }) => {
  const organization = { id: "boundary-org", name: "Recovery workspace", slug: "recovery", subscription_tier: "free" };
  let broken = true;
  let reports = 0;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/telemetry/browser")) {
      const data = route.request().postDataJSON();
      expect(Object.keys(data).sort()).toEqual(["event_id", "kind", "route"]);
      reports++;
      return route.fulfill({ status: 202, body: "" });
    }
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "boundary-user", email: "boundary@example.com", is_active: true, onboarding_completed: true, product_role: "student", home_path: "/check", active_organization_id: organization.id, organizations: [{ organization_id: organization.id, role: "owner", is_active: true }] } });
    if (path.endsWith("/organizations")) return route.fulfill({ json: [organization] });
    if (path.endsWith("/select")) return route.fulfill({ json: organization });
    if (path.endsWith("/usage")) return route.fulfill({ json: { period: "2026-09", limits: broken ? {} : [], recent_operations: [], billing_enabled: false } });
    return route.fulfill({ status: 404, json: { detail: "Fixture endpoint unavailable" } });
  });
  await page.goto("/settings?tab=workspace");
  const heading = page.getByRole("heading", { name: "This page could not load" });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused();
  await expect.poll(() => reports).toBeGreaterThan(0);
  broken = false;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Workspace usage" })).toBeVisible();
});
