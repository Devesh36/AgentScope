import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
let stopping = false;
process.once("SIGTERM", () => { stopping = true; });
process.once("SIGINT", () => { stopping = true; });
process.once("exit", (code) => {
  if (stopping && [0, 130, 143].includes(code)) console.info("AgentScope dashboard graceful shutdown complete");
});
for (const name of ["AGENTSCOPE_TOKEN_FILE", "DASHBOARD_PASSWORD_FILE"]) {
  try {
    if (!process.env[name] || !readFileSync(process.env[name], "utf8").trim()) throw new Error();
  } catch {
    console.error(`AgentScope startup failed: required secret file unavailable (${name})`);
    process.exit(1);
  }
}
try {
  const url = new URL(process.env.API_URL);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error();
} catch {
  console.error("AgentScope startup failed: API_URL is required and must not contain credentials");
  process.exit(1);
}
createRequire(import.meta.url)("/app/apps/web/server.js");
