import { expect, test, type Page } from "@playwright/test";

const personal = { id: "personal", name: "Personal workspace", slug: "personal", subscription_tier: "free" };
const team = { id: "team", name: "Research team", slug: "research-team", subscription_tier: "free" };
const roleHomes = { student: "/check", teacher: "/documents", professor: "/documents", researcher: "/citations", reviewer: "/documents", institution: "/documents" } as const;

async function mockWorkspace(page: Page, options: { onboarded?: boolean; empty?: boolean; revoked?: boolean; failSwitch?: boolean; expired?: boolean } = {}) {
  let organizations = options.empty ? [] : [personal, team];
  let active = options.revoked ? team.id : personal.id;
  let onboarded = options.onboarded ?? true;
  let productRole: keyof typeof roleHomes = "student";
  let failSwitch = options.failSwitch;
  const selected: string[] = [];
  let documentRequests = 0;
  let expired = options.expired;
  let refreshRequests = 0;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const profile = () => ({ id: "user-one", email: "reader@example.com", first_name: "Reader", is_active: true, is_verified: false, active_organization_id: active, product_role: productRole, onboarding_completed: onboarded, home_path: roleHomes[productRole], organizations: organizations.map((organization) => ({ organization_id: organization.id, role: "owner", is_active: true })) });
    if (path.endsWith("/auth/refresh")) {
      expect(request.postDataJSON()).toEqual({});
      refreshRequests += 1;
      expired = false;
      return route.fulfill({ json: { user: profile(), token_type: "bearer", expires_in: 900 } });
    }
    if (path.endsWith("/auth/me")) {
      if (expired) return route.fulfill({ status: 401, json: { detail: "Expired access cookie" } });
      return route.fulfill({ json: profile() });
    }
    if (path.endsWith("/auth/onboarding")) {
      productRole = request.postDataJSON().product_role;
      onboarded = true; organizations = [personal]; active = personal.id;
      return route.fulfill({ json: profile() });
    }
    if (path.endsWith("/organizations")) {
      if (request.method() === "POST") { organizations = [personal]; return route.fulfill({ status: 201, json: personal }); }
      return route.fulfill({ json: organizations });
    }
    if (path.endsWith("/select")) {
      const id = path.split("/").at(-2)!;
      selected.push(id);
      if (id === team.id && options.revoked) return route.fulfill({ status: 403, json: { detail: "Membership revoked" } });
      if (id === team.id && failSwitch) { failSwitch = false; return route.fulfill({ status: 503, json: { detail: "Workspace service temporarily unavailable" } }); }
      active = id;
      return route.fulfill({ json: organizations.find((organization) => organization.id === id) });
    }
    if (path.endsWith("/documents")) { documentRequests += 1; return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }); }
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return { selected, documentRequests: () => documentRequests, refreshRequests: () => refreshRequests };
}

test("an expired access cookie refreshes with a valid request body and restores the workspace", async ({ page }) => {
  const calls = await mockWorkspace(page, { expired: true });
  await page.goto("/check");
  await expect(page.getByRole("heading", { name: "Check a document" })).toBeVisible();
  expect(calls.refreshRequests()).toBe(1);
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(personal.id);
});

for (const [role, home] of Object.entries(roleHomes)) {
  test(`onboarding gives ${role} the server-provided starting workflow`, async ({ page }) => {
    await mockWorkspace(page, { onboarded: false, empty: true });
    await page.goto("/onboarding");
    await page.getByRole("radio", { name: new RegExp(`^${role} `, "i") }).check();
    await page.getByRole("button", { name: "Create my personal workspace" }).click();
    await expect(page.getByRole("heading", { name: "Your personal workspace is ready." })).toBeVisible();
    await page.getByRole("button", { name: "Continue to my first document" }).click();
    await expect(page).toHaveURL(new RegExp(`${home}$`));
    await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(personal.id);
    await expect(page.getByText("Select a workspace to continue")).toHaveCount(0);
  });
}

test("a document workflow offers workspace creation inline", async ({ page }) => {
  const calls = await mockWorkspace(page, { empty: true });
  await page.goto("/check");
  await expect(page.getByRole("heading", { name: "Create your workspace" })).toBeVisible();
  expect(calls.documentRequests()).toBe(0);
  await page.getByRole("textbox", { name: "Workspace name" }).fill("Personal workspace");
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Check a document" })).toBeVisible();
});

test("revoked recent membership falls back only after server validation", async ({ page }) => {
  const calls = await mockWorkspace(page, { revoked: true });
  await page.goto("/documents");
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(personal.id);
  expect(calls.selected.slice(0, 2)).toEqual([team.id, personal.id]);
  await expect(page.getByRole("option", { name: team.name })).toHaveCount(0);
  await expect(page.getByText("Create your first document or import a file")).toBeVisible();
});

test("failed switching hides tenant data and offers a working retry", async ({ page }) => {
  await mockWorkspace(page, { failSwitch: true });
  await page.goto("/documents");
  await expect(page.getByText("Create your first document or import a file")).toBeVisible();
  await page.getByRole("combobox", { name: "Active workspace" }).selectOption(team.id);
  await expect(page.getByText("Workspace service temporarily unavailable")).toBeVisible();
  await expect(page.getByText("Create your first document or import a file")).toHaveCount(0);
  await page.getByRole("button", { name: /Retry|Try again/ }).click();
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(personal.id);
  await expect(page.getByText("Create your first document or import a file")).toBeVisible();
  await page.getByRole("combobox", { name: "Active workspace" }).selectOption(team.id);
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(team.id);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(team.id);
});

test("cached workspace IDs cannot override the server's active membership", async ({ page }) => {
  const calls = await mockWorkspace(page);
  await page.addInitScript(() => localStorage.setItem("azaeron:recent-workspace:user-one", "foreign-tenant"));
  await page.goto("/check");
  await expect(page.getByRole("combobox", { name: "Active workspace" })).toHaveValue(personal.id);
  expect(calls.selected).not.toContain("foreign-tenant");
});

test("focused workspace navigation exposes five products and honest empty states", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Write better. Check confidently. Understand your work." })).toBeVisible();
  const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
  await expect(navigation.getByRole("link")).toHaveText([
    "Home", "Azaeron AI", "AI Humaniser", "AI Detector", "Plagiarism Checker", "Documents", "History",
  ]);
  await expect(navigation.getByRole("link", { name: "Evidence graph" })).toHaveCount(0);
  await navigation.getByRole("link", { name: "Azaeron AI" }).click();
  await expect(page.getByText("Private AI is being prepared")).toBeVisible();
  await expect(page.getByText(/will not be sent to an outside AI provider/)).toBeVisible();
  await navigation.getByRole("link", { name: "AI Detector" }).click();
  await expect(page.getByText("Paste text or choose a document to analyse")).toBeVisible();
  await navigation.getByRole("link", { name: "Plagiarism Checker" }).click();
  await expect(page.getByText("Upload or paste content to check for matching text")).toBeVisible();
  await navigation.getByRole("link", { name: "History" }).click();
  await expect(page.getByText("No history yet")).toBeVisible();
  await page.goto("/write");
  await expect(navigation.getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
});
