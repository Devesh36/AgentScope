# AgentScope landing page

Standalone Next.js marketing site for Vercel. Its static export requires no API,
database, authentication token or environment variables. The observability app
remains separately in `apps/web`; do not select that directory for this deployment.

## Vercel import

1. In Vercel, choose **Add New → Project** and import `Devesh36/AgentScope`.
2. Select branch **feat/local-container-acceptance**. If configuring an existing
   project, set this as its Production Branch in Git settings.
3. Set **Root Directory** to **apps/landing**.
4. Use the **Next.js** framework preset and **Node.js 24.x**.
5. Leave the output directory automatic. `next.config.ts` uses `output: "export"`;
   Next.js produces static files in `out/`. The checked-in `vercel.json` selects
   `npm ci --no-audit --no-fund` and `npm run build && npm run verify`.
6. No environment variables are needed. Click **Deploy**.

No files outside the Root Directory need to be included in the build. No runtime
functions, backend redirects or catch-all rewrites are configured. Unknown paths
such as `/dashboard` and `/api/v1/projects` should return 404. The site's demo
link scrolls to the labeled illustrative REPL session; the real demo runs against
the user's existing AgentScope server.

After deployment, check the homepage on desktop and mobile, switch the uv/Homebrew
install tabs and copy their commands. Confirm the favicon loads and the unavailable
dashboard/API paths return 404. A public Vercel URL has not been created by the
local build; deployment requires your authenticated Vercel account.

## Local build

Requires Node.js 24.x and npm.

```bash
npm --prefix apps/landing ci
npm --prefix apps/landing run build
npm --prefix apps/landing run typecheck
npm --prefix apps/landing run verify
# Optional loopback preview of the exported files:
python3 -m http.server 13020 --bind 127.0.0.1 --directory apps/landing/out
```

Only `out/` is published. `.next/`, `node_modules/`, `.vercel/` and local environment
files stay out of source control. CI validates the static export independently of
the observability stack. This app keeps its marketing assets locally so the Vercel
build is independent of `apps/web` and its container build configuration.

Local validation passed: clean locked npm installation, production export,
TypeScript, the route/configuration guard, and desktop/mobile browser checks for
demo navigation, both install tabs and clipboard, favicon, zero API calls, and
404 responses for application URLs. The exported site is approximately 1.2 MiB.
Hosted Vercel deployment and hosted CI results have not been verified here.
