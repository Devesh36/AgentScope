import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const app = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(resolve(app, ".next/server/app-paths-manifest.json"), "utf8"));
const allowed = new Set(["/page", "/icon.svg/route", "/_not-found/page", "/_global-error/page"]);
assert(Object.keys(manifest).every((route) => allowed.has(route)), "Landing build includes an unexpected route");
const html = await readFile(resolve(app, "out/index.html"), "utf8");
assert(html.includes("Your agents run."), "Landing page was not exported");
assert(!/href="\/(?:dashboard|api|simulation|settings|agents|runs|incidents|investigations)(?:[/?"#])/.test(html), "Landing page links to an unavailable application route");

async function checkFiles(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) await checkFiles(path);
    else if (/\.(?:html|js|json|txt|css)$/.test(entry.name)) {
      const content = await readFile(path, "utf8");
      assert(!/AGENTSCOPE_ADMIN_TOKEN|DASHBOARD_PASSWORD|AGENTSCOPE_TOKEN_FILE/.test(content), "Privileged application configuration appears in static output");
    }
  }
}
await checkFiles(resolve(app, "out"));
console.log("Landing-only static export verified: no dashboard/API routes or privileged configuration.");
