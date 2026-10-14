import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";

let projectId = "";
let emptyProjectId = "";
test.beforeAll(async ({ request }) => {
  const response = await request.post("/api/v1/projects", { data: { name: `Explorer acceptance ${Date.now()}` } });
  expect(response.ok()).toBeTruthy();
  projectId = (await response.json()).id;
  const empty = await request.post("/api/v1/projects", { data: { name: `Empty explorer ${Date.now()}` } });
  expect(empty.ok()).toBeTruthy();
  emptyProjectId = (await empty.json()).id;
  const headers = { "X-Project-ID": projectId };
  const agentResponse = await request.post("/api/v1/agents", { headers, data: { name: "Explorer fixture", framework: "Custom", environment: "development" } });
  expect(agentResponse.ok()).toBeTruthy();
  const agent = await agentResponse.json();
  const events = Array.from({ length: 25 }, (_, index) => {
    const started = Date.now() - (index + 1) * 1000;
    return { event_id: randomUUID(), agent_id: agent.id, run_id: randomUUID(), trace_id: randomUUID().replaceAll("-", ""), span_id: randomUUID().replaceAll("-", "").slice(0, 16), kind: "agent", name: "Explorer fixture", run_name: `Quality run ${String(index + 1).padStart(2, "0")}`, status: "completed", started_at: new Date(started).toISOString(), ended_at: new Date(started + 10).toISOString() };
  });
  expect((await request.post("/api/v1/telemetry/events", { headers, data: { events } })).status()).toBe(202);
  expect((await request.post("/api/v1/simulations", { headers, data: { scenario: "tool_loop" } })).ok()).toBeTruthy();
});

test("run views survive reload, restore history, and reset pages on project changes", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/runs?project=${projectId}&status=completed&source=live&hours=168&page=2`);
  const pagination = page.getByRole("navigation", { name: "Results pagination" });
  await expect(pagination).toContainText("21–25 of 25 results");
  await expect(page.locator("tbody tr")).toHaveCount(5);
  await page.reload();
  await expect(page.getByLabel("Time range")).toHaveValue("168");
  await expect(pagination).toContainText("21–25 of 25 results");
  await page.getByLabel("Run status").selectOption("failed");
  await expect(page.getByRole("heading", { name: "No runs in this view" })).toBeVisible();
  expect(new URL(page.url()).searchParams.has("page")).toBe(false);
  await page.goBack();
  await expect(page.getByLabel("Run status")).toHaveValue("completed");
  await expect(pagination).toContainText("21–25 of 25 results");
  await page.getByLabel("Project", { exact: true }).selectOption(emptyProjectId);
  await expect(page.getByRole("heading", { name: "No runs in this view" })).toBeVisible();
  expect(new URL(page.url()).searchParams.has("page")).toBe(false);
  await page.goBack();
  await expect(page.getByLabel("Project", { exact: true })).toHaveValue(projectId);
  await expect(pagination).toContainText("21–25 of 25 results");

  const searches: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/runs" && url.searchParams.get("search")) searches.push(url.searchParams.get("search")!);
  });
  await page.getByLabel("Search runs").fill("Quality");
  await page.getByLabel("Search runs").fill("Quality run 23");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody tr")).toContainText("Quality run 23");
  expect(searches).toContain("Quality run 23");
  expect(searches).not.toContain("Quality");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "Copy view link" }).click();
  const shared = await page.evaluate(() => navigator.clipboard.readText());
  expect(new URL(shared).searchParams.get("project")).toBe(projectId);
  expect(new URL(shared).searchParams.get("q")).toBe("Quality run 23");
  await page.goto(shared);
  await expect(page.getByLabel("Search runs")).toHaveValue("Quality run 23");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Reset filters", exact: true }).click();
  await expect(page.getByLabel("Search runs")).toHaveValue("");
  await expect(pagination).toContainText("1–20 of 25 results");
  // Reset must also cancel a search that has not reached its debounce timeout.
  await page.getByLabel("Search runs").fill("pending search");
  await page.locator(".page-actions").getByRole("button", { name: "Reset filters", exact: true }).click();
  await expect(page.getByLabel("Search runs")).toHaveValue("");
  await page.goto(`/runs?project=${projectId}&page=99999&source=live`);
  await page.getByRole("button", { name: "Return to first page" }).click();
  await expect(pagination).toContainText("1–20 of 25 results");
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  expect(errors).toEqual([]);
});

test("incident search, severity and sort persist and can be reset", async ({ page }) => {
  await page.goto(`/incidents?project=${projectId}&status=all&severity=critical&sort=oldest&q=Repeated`);
  await expect(page.getByLabel("Incident status")).toHaveValue("all");
  await expect(page.getByLabel("Incident severity")).toHaveValue("critical");
  await expect(page.getByLabel("Sort incidents")).toHaveValue("oldest");
  await expect(page.getByLabel("Search incidents")).toHaveValue("Repeated");
  await page.reload();
  await expect(page.getByLabel("Incident severity")).toHaveValue("critical");
  await page.locator(".page-actions").getByRole("button", { name: "Reset filters", exact: true }).click();
  await expect(page.getByLabel("Incident status")).toHaveValue("active");
  await expect(page.getByLabel("Incident severity")).toHaveValue("all");
  await expect(page.getByLabel("Sort incidents")).toHaveValue("newest");
  await expect(page.getByLabel("Search incidents")).toHaveValue("");
  await expect(page.getByRole("link", { name: /^Repeated tool calls without progress/ }).first()).toBeVisible();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
