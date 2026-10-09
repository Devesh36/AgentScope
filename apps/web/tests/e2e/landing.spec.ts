import { test, expect } from "@playwright/test";

test("public landing page works offline, installation tabs copy commands, mobile stays usable", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, httpCredentials: { username: "landing-test", password: "invalid" }, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  const apiCalls: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/**", (route) => { apiCalls.push(route.request().url()); return route.abort(); });
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Your agents run. Know what happens." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open dashboard" })).toHaveAttribute("href", "/dashboard");
  await page.getByRole("link", { name: "Get AgentScope" }).click();
  await expect(page.getByRole("tab", { name: "uv", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "Copy install command" }).click();
  await expect(page.getByRole("status")).toHaveText("Copied install command.");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("uv tool install");
  await page.getByRole("tab", { name: "Homebrew", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText("brew tap Devesh36/agentscope");
  await page.getByRole("button", { name: "Copy install command" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("brew install Devesh36/agentscope/agentscope");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Open dashboard" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(apiCalls).toEqual([]);
  expect(errors).toEqual([]);
  // Environments enabling dashboard authentication must keep every privileged route protected.
  if (process.env.DASHBOARD_PASSWORD_FILE || process.env.DASHBOARD_PASSWORD) {
    // Node fetch is independent of Playwright's inherited httpCredentials.
    const anonymousStatus = async (path: string) => {
      const response = await fetch(new URL(path, baseURL));
      await response.arrayBuffer();
      return response.status;
    };
    expect(await anonymousStatus("/")).toBe(200);
    expect(await anonymousStatus("/dashboard")).toBe(401);
    expect(await anonymousStatus("/api/v1/projects")).toBe(401);
    expect(await anonymousStatus("/settings")).toBe(401);
  }
  await context.close();
});
