import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
let projectId = "";
const apiUrl = process.env.API_URL || "http://127.0.0.1:8000";
test.beforeAll(async ({ request }) => {
  const token =
    process.env.AGENTSCOPE_ADMIN_TOKEN ||
    (
      await readFile(process.env.AGENTSCOPE_ADMIN_TOKEN_FILE || resolve(process.cwd(), "../../.local/admin-token"), "utf8")
    ).trim();
  const response = await request.post(`${apiUrl}/api/v1/projects`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: `Browser validation ${Date.now()}` },
  });
  expect(response.ok()).toBeTruthy();
  projectId = (await response.json()).id;
});
test("complete observability, investigation, approval, and recovery workflow", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Project", { exact: true }).selectOption(projectId);
  await expect(
    page.getByText("Ready to receive your first trace"),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No active incidents" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Simulation lab", exact: false })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Real pipeline. Synthetic telemetry." }),
  ).toBeVisible();
  await page
    .locator(".scenario-card")
    .filter({
      has: page.getByRole("heading", { name: "Tool-call loop", exact: true }),
    })
    .getByRole("button", { name: "Run scenario" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Scenario recorded: tool loop" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "View incidents", exact: true }).click();
  await expect(
    page.getByRole("link", { name: /^Repeated tool calls without progress/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: /^Repeated tool calls without progress/ })
    .click();
  await page.getByRole("button", { name: "Investigate incident" }).click();
  await expect(
    page.getByRole("heading", { name: "Investigation complete", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Decision summary", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".evidence-card")).toHaveCount(8);
  await page.getByRole("button", { name: "Hypotheses", exact: true }).click();
  await expect(
    page
      .locator(".hypothesis-card")
      .getByRole("heading", {
        name: "The retry path is reprocessing unchanged results without a recorded progress event.",
        exact: true,
      }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve proposal", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Approve proposal", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Execute demo action", exact: true }),
  ).toBeVisible();
  const investigationPath = new URL(page.url()).pathname;
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Remediation policies" }).click();
  await page
    .getByRole("checkbox", { name: "Allow isolated demo control" })
    .check();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByText("Project settings saved", { exact: true }),
  ).toBeVisible();
  await page.goto(investigationPath);
  await page
    .getByRole("button", { name: "Execute demo action", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Execute demo action", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Recovery verification in progress",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "verified recovered", exact: true }),
  ).toBeVisible({ timeout: 25000 });
  await page.getByRole("link", { name: /Inspect follow-up run/ }).click();
  await expect(
    page.getByRole("heading", {
      name: "Verify synthetic recovery",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".waterfall-row")).toHaveCount(2);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByText("Your agents are operating normally"),
  ).toBeVisible();
  await expect(page.locator(".chart-box svg").first()).toBeVisible();
  await page.screenshot({
    path: resolve(process.env.PLAYWRIGHT_SCREENSHOT_DIR || "../../.local", "overview-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: resolve(process.env.PLAYWRIGHT_SCREENSHOT_DIR || "../../.local", "overview-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Agents", exact: true }).click();
  await expect(page.locator(".agent-card")).toHaveCount(4);
  expect(errors).toEqual([]);
});
test("settings keys are shown once and can be revoked", async ({ page }) => {
  await page.goto("/settings");
  await page.getByLabel("Project", { exact: true }).selectOption(projectId);
  await page.getByRole("button", { name: "API keys", exact: true }).click();
  await page
    .getByRole("button", { name: "Create API key", exact: true })
    .click();
  await page.getByLabel("Key name", { exact: true }).fill("browser-test-sdk");
  await page.getByRole("button", { name: "Create key", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Save your API key" }),
  ).toBeVisible();
  expect(await page.locator(".secret-reveal code").evaluate((node) => node.textContent?.startsWith("as_"))).toBe(true);
  await page.getByRole("button", { name: "I saved the key" }).click();
  await expect(page.locator(".secret-reveal")).toHaveCount(0);
  await page
    .getByRole("row")
    .filter({ hasText: "browser-test-sdk" })
    .getByRole("button", { name: "Revoke", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Revoke key", exact: true })
    .click();
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "browser-test-sdk" })
      .getByText("revoked", { exact: true }),
  ).toBeVisible();
});
