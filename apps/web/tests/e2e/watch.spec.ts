import { randomUUID } from "node:crypto";
import { test, expect } from "@playwright/test";

test("watch dashboard selects its project and distinguishes live calls from grounding assessments", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const previous = (await (await request.get("/api/v1/projects")).json())[0].id;
  const project = await (await request.post("/api/v1/projects", { data: { name: `Watch browser validation ${randomUUID().slice(0, 8)}` } })).json();
  const headers = { "X-Project-ID": project.id };
  const agent = await (await request.post("/api/v1/agents", { headers, data: { name: "Browser watch validation", framework: "Automatic LLM instrumentation" } })).json();
  const session = { repository: "example-project", session_id: randomUUID(), status: "waiting" };
  expect((await request.put(`/api/v1/agents/${agent.id}/watch`, { headers, data: session })).status()).toBe(200);
  await page.addInitScript((id) => localStorage.setItem("agentscope-project", id), previous);
  await page.goto(`/dashboard?project=${project.id}`);
  const metric = (name: string) => page.locator(".metric-card").filter({ has: page.locator(".metric-label", { hasText: name }) }).locator(".metric-value");
  await expect(page.getByRole("heading", { name: "Local project monitoring" })).toBeVisible();
  await expect(page.locator(".watch-session strong")).toHaveText("example-project");
  await expect(metric("LLM calls")).toHaveText("0");
  await expect(metric("Unsupported claims")).toHaveText("Not evaluated");
  const started = new Date().toISOString();
  const root = { event_id: randomUUID(), agent_id: agent.id, run_id: randomUUID(), trace_id: randomUUID().replaceAll("-", ""), span_id: "1".repeat(16), name: "Observed application call", kind: "agent", status: "running", started_at: started };
  const llm = { ...root, event_id: randomUUID(), span_id: "2".repeat(16), parent_span_id: root.span_id, kind: "llm", model: "gpt-4o-mini", attributes: { usage_observed: false } };
  expect((await request.post("/api/v1/telemetry/events", { headers, data: { events: [root, llm] } })).status()).toBe(202);
  await request.put(`/api/v1/agents/${agent.id}/watch`, { headers, data: { ...session, status: "monitoring" } });
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(metric("LLM calls")).toHaveText("1");
  await expect(page.getByText("Application running · capturing supported LLM calls", { exact: true })).toBeVisible();
  await expect(metric("Unsupported claims")).toHaveText("Not evaluated");
  const completed = { status: "completed", ended_at: new Date().toISOString() };
  const evaluated = { ...llm, ...completed, event_id: randomUUID(), input_tokens: 11, output_tokens: 7, attributes: { usage_observed: true, grounding: { unsupported_claims: 2, evaluator: "browser-reference-check" } } };
  await request.post("/api/v1/telemetry/events", { headers, data: { events: [evaluated, { ...root, ...completed, event_id: randomUUID() }] } });
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(metric("Unsupported claims")).toHaveText("2");
  await expect(metric("Tokens consumed")).toHaveText("18");
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  await request.put(`/api/v1/agents/${agent.id}/watch`, { headers, data: { ...session, status: "stopped" } });
  expect(errors).toEqual([]);
});
