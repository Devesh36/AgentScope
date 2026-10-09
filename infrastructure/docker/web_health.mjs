import { readFileSync } from "node:fs";
try {
  const password = readFileSync(process.env.DASHBOARD_PASSWORD_FILE, "utf8").trim();
  const response = await fetch("http://127.0.0.1:3000/api/health/ready", {
    headers: { Authorization: `Basic ${Buffer.from(`admin:${password}`).toString("base64")}` },
    signal: AbortSignal.timeout(5000),
  });
  const data = await response.json();
  if (!response.ok || data.status !== "ready" || data.storage !== "postgresql") throw new Error();
} catch {
  console.error("Dashboard or upstream API is not ready");
  process.exit(1);
}
