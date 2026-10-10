import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const app = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(resolve(app, ".next/server/app-paths-manifest.json"), "utf8"));
const allowed = new Set(["/page", "/docs/page", "/icon.svg/route", "/_not-found/page", "/_global-error/page"]);
assert(Object.keys(manifest).every((route) => allowed.has(route)), "Landing build includes an unexpected route");
const html = await readFile(resolve(app, "out/index.html"), "utf8");
assert(html.includes("Your agents run."), "Landing page was not exported");
assert(html.includes('href="/docs"'), "Landing page does not link to documentation");
assert(html.includes('href="#phase"') && html.includes('id="phase"'), "Landing page does not include the Phase navigation and timeline");
const history = JSON.parse(await readFile(resolve(app, "lib/development-phases.json"), "utf8"));
for (const change of history.commits) {
  assert(html.includes(change.title), `Development history omits: ${change.title}`);
  if (change.sha) assert(html.includes(`/commit/${change.sha}`), "Development history omits a source commit link");
}
const documentation = await readFile(resolve(app, "out/docs.html"), "utf8");
assert(documentation.includes("What is AgentScope?"), "Documentation page was not exported");
for (const screenshot of ["cli-start", "cli-demo"]) {
  const bytes = await readFile(resolve(app, `out/docs-assets/${screenshot}.png`));
  assert(bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), "Documentation screenshot is not a PNG");
  assert(documentation.includes(`/docs-assets/${screenshot}.png`), "Documentation does not include the terminal screenshot");
}
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
console.log("Public homepage and documentation export verified: terminal screenshots included, no dashboard/API routes or privileged configuration.");
