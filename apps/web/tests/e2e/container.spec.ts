import { test, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const state = process.env.AGENTSCOPE_ACCEPTANCE_STATE;
test("container restart preserves real telemetry, audit, settings and reconnects the dashboard", async ({ page, request }) => {
  test.skip(!state, "Only runs against a dedicated container acceptance stack");
  test.setTimeout(120000);
  const root = resolve(process.cwd(), "../..");
  const sdk = JSON.parse(await readFile(resolve(state!, "sdk.json"), "utf8"));
  const token = (await readFile(process.env.AGENTSCOPE_ADMIN_TOKEN_FILE!, "utf8")).trim();
  const headers = { Authorization: `Bearer ${token}`, "X-Project-ID": sdk.project };
  const api = process.env.API_URL!;
  await page.addInitScript(() => {
    const Original = window.EventSource;
    (window as unknown as { acceptanceSSE: { opens: number; errors: number; refreshes: number } }).acceptanceSSE = { opens: 0, errors: 0, refreshes: 0 };
    const counters = (window as unknown as { acceptanceSSE: { opens: number; errors: number; refreshes: number } }).acceptanceSSE;
    window.EventSource = class extends Original {
      constructor(url: string | URL, options?: EventSourceInit) {
        super(url, options);
        this.addEventListener("open", () => counters.opens++);
        this.addEventListener("error", () => counters.errors++);
        this.addEventListener("refresh", () => counters.refreshes++);
      }
    };
  });
  await page.goto("/");
  await page.getByLabel("Project", { exact: true }).selectOption(sdk.project);
  await expect(page.getByText("container-calculator", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("LIVE TELEMETRY UPDATES", { exact: true })).toBeVisible();
  const before = await page.evaluate(() => ({ ...(window as unknown as { acceptanceSSE: { opens: number; errors: number; refreshes: number } }).acceptanceSSE }));
  await promisify(execFile)(resolve(root, ".venv/bin/python"), [resolve(root, "scripts/container_acceptance.py"), "restart", "--state", state!], { timeout: 90000 });
  await expect(page.getByText("LIVE TELEMETRY UPDATES", { exact: true })).toBeVisible({ timeout: 30000 });
  await expect.poll(async () => page.evaluate(() => (window as unknown as { acceptanceSSE: { opens: number } }).acceptanceSSE.opens)).toBeGreaterThan(before.opens);
  await expect.poll(async () => page.evaluate(() => (window as unknown as { acceptanceSSE: { refreshes: number } }).acceptanceSSE.refreshes)).toBeGreaterThan(before.refreshes);
  const counters = await page.evaluate(() => (window as unknown as { acceptanceSSE: { opens: number; errors: number; refreshes: number } }).acceptanceSSE);
  const trace = await request.get(`${api}/api/v1/runs/${sdk.run}/trace`, { headers });
  expect(trace.ok()).toBeTruthy();
  expect((await trace.json()).spans).toHaveLength(3);
  const replay = await request.post(`${api}/api/v1/telemetry/events`, { headers, data: { events: sdk.events } });
  expect(replay.status()).toBe(202);
  expect((await replay.json()).accepted).toBe(0);
  // Repeated approval/execution must not create another action, audit, or follow-up.
  const projects = await (await request.get(`${api}/api/v1/projects`, { headers })).json();
  const browserProject = projects.find((p: { name: string }) => p.name.startsWith("Browser validation"));
  const browserHeaders = { ...headers, "X-Project-ID": browserProject.id };
  const investigations = await (await request.get(`${api}/api/v1/investigations`, { headers: browserHeaders })).json();
  const investigation = await (await request.get(`${api}/api/v1/investigations/${investigations[0].id}`, { headers: browserHeaders })).json();
  const remediation = investigation.incident.remediation;
  expect(remediation.verification.result).toBe("VERIFIED_RECOVERED");
  const detailBefore = investigation.incident;
  for (const action of ["approve", "execute", "execute"]) {
    const result = await request.post(`${api}/api/v1/remediations/${remediation.id}/${action}`, { headers: browserHeaders });
    expect(result.ok()).toBeTruthy();
  }
  const detailAfter = await (await request.get(`${api}/api/v1/incidents/${detailBefore.id}`, { headers: browserHeaders })).json();
  expect(detailAfter.audit).toEqual(detailBefore.audit);
  expect(detailAfter.remediation).toEqual(remediation);
  const followUpId = remediation.verification.evidence_ids[0];
  const followUp = await (await request.get(`${api}/api/v1/runs/${followUpId}`, { headers: browserHeaders })).json();
  expect(Date.parse(followUp.started_at)).toBeGreaterThanOrEqual(Date.parse(remediation.executed_at));
  expect(Date.parse(remediation.verification.checked_at) - Date.parse(remediation.executed_at)).toBeGreaterThanOrEqual(15000);
  await writeFile(resolve(state!, "browser-reconnection.json"), JSON.stringify({ before, after: counters, replayAccepted: 0, duplicateActions: 0 }, null, 2));
});
