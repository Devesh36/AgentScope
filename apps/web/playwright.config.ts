import { defineConfig } from "@playwright/test";
import chromium from "@sparticuz/chromium";
import { resolve } from "node:path";
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    headless: true,
    launchOptions: {
      executablePath: "/tmp/chromium",
      args: chromium.args.filter((arg) => arg !== "--single-process"),
      env: {
        ...process.env,
        XDG_CACHE_HOME: resolve(process.cwd(), "../../.local/cache"),
      },
    },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
