import { createHmac, randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";
import axe from "axe-core";
import { postWithRetryAfter } from "./live-request";

test.use({ actionTimeout: 15_000 });

// Independent RFC 6238 test client. Application OTP verification uses cryptography.
function authenticatorCode(secret: string) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...secret.replace(/=/g, "")].map((letter) => alphabet.indexOf(letter).toString(2).padStart(5, "0")).join("");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  return ((digest.readUInt32BE(digest[19] & 15) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
}

test("real SMTP verification, MFA recovery login, password reset and device revocation", async ({ page, browser, baseURL }) => {
  test.skip(process.env.RUN_LIVE_E2E !== "1", "Requires the isolated migrated runtime and local mail sink");
  test.setTimeout(240_000);
  const mailBase = process.env.MAILPIT_URL;
  expect(mailBase, "Live identity gate requires MAILPIT_URL and the periodic sender").toBeTruthy();
  const credentials = { email: `identity-browser-${Date.now()}@example.com`, password: randomBytes(18).toString("hex") + "Aa1!" };
  const headers = { Origin: baseURL! };
  async function submitLogin() {
    for (let attempt = 0; attempt < 2; attempt++) {
      const pending = page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      const response = await pending;
      if (response.status() !== 429) return;
      const retry = Number(response.headers()["retry-after"]);
      expect(retry).toBeGreaterThan(0);
      expect(retry).toBeLessThanOrEqual(60);
      await page.waitForTimeout((retry + 1) * 1000);
    }
    throw new Error("Authentication remained rate limited after Retry-After");
  }
  expect((await postWithRetryAfter(page.request, "/api/v1/auth/register", { headers, data: credentials })).status()).toBe(201);
  await page.goto("/login");
  await page.getByLabel("Work email").fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await submitLogin();
  await expect(page).toHaveURL(/onboarding/);
  expect((await page.request.post("/api/v1/auth/onboarding", { headers, data: { product_role: "student" } })).ok()).toBeTruthy();
  await page.goto("/settings?tab=security");

  async function linkFromMail(subject: string) {
    let messageId = "";
    await expect.poll(async () => {
      const response = await page.request.get(mailBase + "/api/v1/messages");
      const data = await response.json();
      const message = data.messages.find((item: { ID: string; Subject: string; To: Array<{ Address: string }> }) => item.Subject === subject && item.To.some((to) => to.Address === credentials.email));
      messageId = message?.ID || "";
      return !!messageId;
    }, { timeout: 60_000, intervals: [1000, 2000, 3000] }).toBe(true);
    const message = await (await page.request.get(mailBase + "/api/v1/message/" + messageId)).json();
    return message.Text.match(/http[^\s]+#token=[A-Za-z0-9_-]+/)[0] as string;
  }

  await page.getByRole("button", { name: "Send verification email" }).click();
  const verificationLink = await linkFromMail("Verify your Azaeron email");
  await page.goto(verificationLink);
  await expect(page).toHaveURL(/\/verify-email$/);
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Email verified.");
  await page.goto("/settings?tab=security");
  await expect(page.getByText("Email: Verified", { exact: true })).toBeVisible();
  await page.getByLabel("Current password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Set up MFA" }).click();
  const setupSecret = await page.getByLabel("Authenticator setup secret", { exact: true }).inputValue();
  await page.getByLabel("Authenticator or recovery code", { exact: true }).fill(authenticatorCode(setupSecret));
  await page.getByRole("button", { name: "Confirm authenticator" }).click();
  const recoveryField = page.getByLabel("Recovery codes — save now", { exact: true });
  await expect(recoveryField).toBeVisible();
  const recovery = (await recoveryField.inputValue()).split("\n");
  expect(recovery).toHaveLength(10);
  const browserStorage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(browserStorage).not.toContain(setupSecret);
  expect(browserStorage).not.toContain(recovery[0]);
  await page.getByRole("button", { name: "I saved the recovery codes" }).click();
  await expect(recoveryField).toHaveCount(0);
  await page.reload();
  await expect(recoveryField).toHaveCount(0);

  await page.goto("/login");
  await page.getByLabel("Work email").fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await submitLogin();
  await page.getByLabel("Authenticator or recovery code", { exact: true }).fill(recovery[0]);
  await submitLogin();
  await expect(page).toHaveURL(/\/check$/);

  await page.goto("/forgot-password");
  await page.getByLabel("Account email").fill(credentials.email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If this account exists");
  const resetLink = await linkFromMail("Azaeron password reset");
  await page.goto(resetLink);
  await expect(page).toHaveURL(/\/reset-password$/);
  const newPassword = randomBytes(18).toString("hex") + "Aa1!";
  await page.getByLabel("New password", { exact: true }).fill(newPassword);
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByRole("status")).toContainText("Password reset.");
  await page.getByRole("link", { name: "Return to sign in" }).click();
  await page.getByLabel("Work email").fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(newPassword);
  await submitLogin();
  await page.getByLabel("Authenticator or recovery code", { exact: true }).fill(recovery[1]);
  await submitLogin();
  await expect(page).toHaveURL(/\/check$/);

  const second = await browser.newContext({ baseURL });
  try {
    const secondLogin = () => second.request.post("/api/v1/auth/login", { headers, data: { email: credentials.email, password: newPassword, mfa_code: recovery[2] } });
    let response = await secondLogin();
    if (response.status() === 429) {
      const retry = Number(response.headers()["retry-after"]);
      expect(retry).toBeGreaterThan(0);
      expect(retry).toBeLessThanOrEqual(60);
      await page.waitForTimeout((retry + 1) * 1000);
      response = await secondLogin();
    }
    expect(response.status()).toBe(200);
    await page.goto("/settings?tab=security");
    await page.getByRole("button", { name: /Revoke session from/ }).click();
    await expect(page.getByRole("status").first()).toContainText("Session revoked.");
    expect((await second.request.get("/api/v1/auth/me")).status()).toBe(401);
    await page.addScriptTag({ content: axe.source });
    const result = await page.evaluate(async () => (window as unknown as { axe: typeof axe }).axe.run("section[aria-labelledby='identity-heading']"));
    expect(result.violations).toEqual([]);
  } finally { await second.close(); }
});
