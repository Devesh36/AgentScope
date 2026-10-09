# Local container acceptance

This increment preserves the Next.js/FastAPI modular monolith. PostgreSQL stores telemetry and its transactional outbox, investigations, approvals, audit history and settings. One API worker runs the existing deterministic LangGraph investigation and recovery verifier. The web server proxies authenticated API/SSE requests. Real agents remain recommendation-only; synthetic control requires a separately approved action and the saved demo policy. No live external model credentials are passed to containers.

## Prerequisites

- Linux x86-64, a running local Docker Engine with BuildKit at `/var/run/docker.sock`, and Compose v2 supporting `--wait`, build secrets and resource limits. This path intentionally avoids remote Docker contexts. Rootless/custom sockets, Windows/macOS and ARM browser execution have not been verified.
- Python 3.12, uv, Node.js 24 and npm, with the existing `.venv` and `apps/web/node_modules`. Native checks need the development dependencies. The API and web images supply their own pinned runtimes.
- Outbound verified HTTPS to Docker Hub, `registry.npmjs.org`, `pypi.org` and `files.pythonhosted.org`. Chromium comes from the locked npm dependency; no browser CDN download is required.
- Allow roughly 4 GiB RAM and at least 12 GiB free disk for a first build. Docker's `vfs` storage driver uses substantially more disk for repeated builds; inspect `df -h` and Docker build cache before another build. Do not prune unrelated resources or change daemon/storage/security settings to work around capacity.
- Unused loopback ports 18000 (API) and 13000 (dashboard). PostgreSQL has no host port. Ports can be overridden for concurrent stacks.

For a fresh checkout, install native validation dependencies without migrating or starting a native database:

```bash
export UV_CACHE_DIR="$PWD/.local/cache/uv"
export npm_config_cache="$PWD/.local/cache/npm"
uv venv --python 3.12
uv pip sync --require-hashes apps/api/requirements.txt
uv pip install --no-deps -e packages/python-sdk
npm --prefix apps/web ci --no-audit --no-fund
```

Reuse an existing environment; do not replace its virtual environment or checkout. Python versions and package hashes are locked in `apps/api/requirements.txt`; npm uses `package-lock.json` integrity hashes. The SDK build backend is pinned. Base images use immutable digests. Updating dependencies is an intentional lockfile change, not part of startup. The initial Alembic revision now contains a frozen schema instead of importing future ORM definitions; it preserves revision `001` and the existing schema.

## Repeatable acceptance command

From the repository root:

```bash
npm run accept:containers
# Alternate unused ports:
npm run accept:containers -- --api-port 18001 --web-port 13001
```

Each invocation generates a fresh `agentscope-accept-<nonce>` project and private state directory. It refuses an occupied port and never accepts an existing database as a fresh first-start test. It does not silently replace real telemetry with simulation data. Success requires all of the following:

1. Native API/SDK tests, Ruff, mypy, TypeScript, Vitest and an isolated native production build. The temporary web source/dependency copy is removed after its build passes; the original `.next` directory is not used for builds.
2. Compose validation, both image builds, actionable missing-configuration exits, PostgreSQL readiness, Alembic `001`, and zero runs on first start.
3. Non-root users, read-only app roots, dropped capabilities, no privilege escalation, explicit memory/CPU/PID bounds, and loopback-only published ports.
4. A database outage returns 503 from both API and dashboard health, without substituting demo runs. An offline SDK export stays within its queue bound and accounts for dropped events before reconnecting the stack.
5. The existing SDK instruments a real calculator, nested tool and progress event over HTTP. An injected lost acknowledgement retries identical event IDs. Persisted trace, metrics, chart aggregates and dashboard-proxy data must agree; replay accepts zero additional events. No model is called, so tokens are zero and cost is unavailable.
6. Browser simulation → evidence-grounded investigation → explicit approval → separate execution → `PENDING` → recovery after at least 15 seconds. Screenshots cover the dashboard at desktop/mobile widths. The key lifecycle test creates and revokes a one-time key.
7. A browser remains open through a complete stack restart. Every record in twelve tables is hashed before/after; database volume identity and hashes must match. SSE reconnects and refreshes without reloading the page. Repeated approval/execution preserves audit history, remediation and follow-up identity. Follow-up timestamps must be at or after intervention.
8. Credentials are absent from own container logs/image metadata; the native state directory and build CA are absent from runtime images. The SDK key is revoked. All services stop within their budget with no OOM or forced kill. The database volume is retained.

Reports have `execution: local`, named pass/fail checks, durations, image IDs, runtime bounds, SDK counters, persistence counts and shutdown evidence. Failure returns nonzero and retains state for diagnosis; it does not delete data or hide a failed step. Generated credentials, telemetry snapshots and private browser outputs must not be uploaded as CI artifacts. Playwright traces and automatic failure screenshots are disabled because they can contain credentials or a revealed API key.

## Manual first start and lifecycle

The initializer creates three disposable credentials in a mode-0700 directory. Secret files are read-only and readable inside non-root containers (Compose's local bind mounts do not implement secret uid/gid overrides). Existing credentials are never changed. Do not print these files, put them in shell history, or export their values. The generated environment file contains paths and ports only.

```bash
AGENTSCOPE_STATE=$(.venv/bin/python scripts/container_acceptance.py init)
export BUILDX_CONFIG="$PWD/.local/cache/buildx"
docker --host=unix:///var/run/docker.sock compose --env-file "$AGENTSCOPE_STATE/stack.env" config --quiet
docker --host=unix:///var/run/docker.sock compose --env-file "$AGENTSCOPE_STATE/stack.env" build
.venv/bin/python scripts/container_acceptance.py up --state "$AGENTSCOPE_STATE"
curl --fail http://127.0.0.1:18000/health/ready
.venv/bin/python scripts/container_acceptance.py restart --state "$AGENTSCOPE_STATE"
.venv/bin/python scripts/container_acceptance.py stop --state "$AGENTSCOPE_STATE"
.venv/bin/python scripts/container_acceptance.py up --state "$AGENTSCOPE_STATE"
```

Use `--api-port`/`--web-port` with `init` to change ports. The browser requires Basic authentication (`admin` and the generated dashboard password). Automated requests read that file internally rather than exposing its value. API project keys are created through Settings or the authenticated API as before.

`up` waits for PostgreSQL, then the API's migrations/database/worker check, then the web check through the real API. Every API start upgrades migrations before accepting requests; a second start reuses the same database. Missing configuration, missing/unreadable/empty secret files, migration errors or unavailable database dependencies produce a nonzero startup with a short diagnostic. Third-party exception text is withheld because it can contain credentials or SQL parameters. There is no SQLite fallback in container mode.

The API stops accepting work and drains its current transaction and SSE requests on SIGTERM. The web proxy cancels upstream streams so Next can finish requests. Uvicorn and Next intentionally report exit 143 after graceful SIGTERM; acceptance requires current-process teardown evidence. Exit 137/OOM/forced shutdown fails acceptance. Browser reconnection uses exponential backoff capped at ten seconds and only refreshes data, never replays mutations.

SDK `queue_size` must be positive; `batch_size` is limited to 1000. `close(timeout)` rejects subsequent events, drains until its deadline, discards remaining queued events with counters, and returns whether its thread terminated. An already active request retains its socket timeout; `False` signals that it is still finishing. Call `close` again to wait. Export retries preserve event IDs so an accepted request with a lost response does not duplicate records.

No command above removes a database volume. To remove stopped **owned containers and their network** while keeping data, use the exact saved environment file:

```bash
docker --host=unix:///var/run/docker.sock compose --env-file "$AGENTSCOPE_STATE/stack.env" down
```

Do not add `--volumes`, prune Docker, use a different project's configuration, or run the destructive API test fixture with `TEST_DATABASE_URL` pointed at this retained database. Acceptance explicitly clears `TEST_DATABASE_URL` for native tests, which use temporary SQLite.

## Managed cloud trust and CI

The initializer combines the system PEM bundle with the session's `CODEX_PROXY_CERT` when supplied. Compose sends this bundle as a BuildKit secret to network-dependent build steps. pip and npm verify HTTPS against it; the bundle is never copied into a layer or mounted at runtime. `BUILDX_CONFIG` keeps builder bookkeeping in a writable workspace directory without changing `DOCKER_CONFIG`, registry credentials, proxy routing or host trust settings.

`.github/workflows/ci.yml` adds an Ubuntu job running the same acceptance command and uploading only sanitized JSON measurements. A workflow committed locally is not evidence of a hosted CI run. No hosted job is triggered by local validation, and no branch is pushed by these scripts.

See [the measured local validation record](container-validation.md) for this increment's results and remaining limitations.
