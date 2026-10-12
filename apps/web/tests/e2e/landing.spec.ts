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
  await page.getByRole("navigation", { name: "Site navigation" }).getByRole("link", { name: "Phase", exact: true }).click();
  await expect(page).toHaveURL(/#phase$/);
  const history = page.getByRole("region", { name: "Phase", exact: true });
  await expect(history.getByRole("heading", { name: "A visible development history" })).toBeVisible();
  await expect(history.getByRole("link", { name: /^View commit 89356ca:/ })).toHaveAttribute("href", "https://github.com/Devesh36/AgentScope/commit/89356caba95c89b6b1efefebacd19e568adaac67");
  await expect(history.getByText("Published product documentation", { exact: true })).toBeVisible();
  await expect(history.locator('time[datetime="2026-10-09"]').first()).toHaveText("9 Oct 2026");
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
  await expect(page.getByRole("navigation", { name: "Site navigation" }).getByRole("link", { name: "Phase", exact: true })).toBeVisible();
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
    expect(await anonymousStatus("/docs")).toBe(200);
    expect(await anonymousStatus("/docs-assets/cli-start.png")).toBe(200);
    expect(await anonymousStatus("/docs-assets/cli-demo.png")).toBe(200);
    expect(await anonymousStatus("/docs/private")).toBe(401);
    expect(await anonymousStatus("/docs-assets/private.png")).toBe(401);
    expect(await anonymousStatus("/dashboard")).toBe(401);
    expect(await anonymousStatus("/api/v1/projects")).toBe(401);
    expect(await anonymousStatus("/settings")).toBe(401);
  }
  await context.close();
});

test("public documentation explains the workflow, serves terminal screenshots, and copies usable commands", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, httpCredentials: { username: "docs-test", password: "invalid" }, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  const errors: string[] = [];
  const apiCalls: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/**", (route) => { apiCalls.push(route.request().url()); return route.abort(); });
  await page.goto("/");
  await page.getByRole("link", { name: "Docs", exact: true }).click();
  await expect(page).toHaveURL(/\/docs$/);
  await expect(page.getByRole("heading", { name: "What is AgentScope?" })).toBeVisible();
  await page.getByRole("link", { name: "Terminal tour", exact: true }).click();
  const tour = page.locator("#terminal-tour");
  const steps = tour.locator("details");
  await expect(steps).toHaveCount(10);
  for (const step of await steps.all()) {
    if ((await step.getAttribute("open")) === null) await step.locator("summary").click();
    const capture = step.locator("img");
    await capture.scrollIntoViewIfNeeded();
    await expect(capture).toBeVisible();
    await expect.poll(() => capture.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBe(1740);
    await step.locator("summary").click();
  }
  await steps.first().locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(steps.first()).toHaveAttribute("open", "");
  await expect(steps.first().getByRole("link", { name: "Open full-size capture: First launch and model setup", exact: true })).toHaveAttribute("href", "/docs-assets/terminal-tour/01-setup.png");
  const downloadReady = page.waitForEvent("download");
  await tour.getByRole("link", { name: "Download the complete PDF tour", exact: true }).click();
  const download = await downloadReady;
  expect(download.suggestedFilename()).toBe("agentscope-terminal-tour.pdf");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).subarray(0, 5).toString()).toBe("%PDF-");
  await page.getByRole("link", { name: "Configure the assistant", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Configure and chat with AgentScope", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Copy Meet your AgentScope assistant", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("agentscope configure");
  await page.getByRole("link", { name: "Connect the CLI", exact: true }).click();
  await page.getByRole("button", { name: "Copy Connect from the checkout", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("--token-file .local/admin-token");
  await page.getByRole("link", { name: "Your first investigation", exact: true }).click();
  for (const source of ["cli-start", "cli-demo"]) {
    const image = page.locator(`img[src="/docs-assets/${source}.png"]`);
    await image.scrollIntoViewIfNeeded();
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBe(1200);
  }
  await page.getByRole("link", { name: "Troubleshooting", exact: true }).click();
  await page.getByText("Authentication fails", { exact: true }).click();
  await expect(page.getByText("A project API key cannot administer the CLI workspace.", { exact: false })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/docs");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.getByRole("navigation", { name: "Documentation sections" })).toBeVisible();
  expect(apiCalls).toEqual([]);
  expect(errors).toEqual([]);
  await context.close();
});
