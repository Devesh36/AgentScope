import { defineConfig } from "@playwright/test";
import chromium from "@sparticuz/chromium";
import { resolve } from "node:path";
import { readFileSync } from "node:fs";
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  projects: process.env.AGENTSCOPE_ACCEPTANCE_STATE ? [
    { name: "workflow", testMatch: ["workflow.spec.ts", "landing.spec.ts", "watch.spec.ts", "explorers.spec.ts"] },
    { name: "restart", testMatch: "container.spec.ts", dependencies: ["workflow"] },
  ] : [{ name: "workflow", testMatch: ["workflow.spec.ts", "landing.spec.ts", "watch.spec.ts", "explorers.spec.ts"] }],
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: "list",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    httpCredentials: process.env.DASHBOARD_PASSWORD_FILE ? {
      username: "admin",
      password: readFileSync(process.env.DASHBOARD_PASSWORD_FILE, "utf8").trim(),
    } : undefined,
    headless: true,
    launchOptions: {
      executablePath: await chromium.executablePath(),
      args: chromium.args.filter((arg) => arg !== "--single-process"),
      env: {
        ...process.env,
        XDG_CACHE_HOME: resolve(process.cwd(), "../../.local/cache"),
      },
    },
    // API keys and Basic credentials must never appear in trace/screenshot artifacts.
    trace: "off",
    screenshot: "off",
  },
});
