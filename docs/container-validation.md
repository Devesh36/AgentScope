# Container validation record — 2026-10-09

All results below were measured locally in the managed Linux x86-64 workspace. Hosted CI has **not** run. The existing application was preserved as baseline commit `89356ca` because the original `work` branch had no commits. Implementation commit `a342698e19dbc5a8735fd0ff638f0590d1987208` was validated on feature branch `feat/local-container-acceptance`. No push, merge, external deployment or publication occurred.

## Reproduce

Prerequisites and manual commands are in [local-containers.md](local-containers.md). The final complete command was:

```bash
npm run accept:containers -- --api-port 18002 --web-port 13002
```

The final project was `agentscope-accept-b472f1696e32`. Its private state and original report are under `.local/container-acceptance/agentscope-accept-b472f1696e32/`. A sanitized copy of the report is committed at [validation/local-container-acceptance.json](validation/local-container-acceptance.json). All 18 named checks passed, totaling **165.26 seconds** of measured check time. The final image-build check reused caches; earlier actual dependency installs and both production compilers also completed successfully with TLS/package hash verification enabled.

| Validation | Measured local result |
| --- | --- |
| Native API/SDK | 21 tests passed in 1.87 s, including 9 new lifecycle/configuration/migration regressions |
| Native web | 3 Vitest tests passed; TypeScript, Ruff and mypy passed |
| Production builds | Isolated native build passed in 12.71 s; both container images built successfully |
| Compose / first start | Configuration valid; all three services healthy in 23.01 s; migration revision `001`; zero initial runs |
| Missing configuration | API and web each exited 1 with an actionable variable-name diagnostic |
| Missing database during startup | Separate `compose run --no-deps -e DATABASE_HOST=127.0.0.1 api` probe exited 1 with `OperationalError`; no credential values or SQLite fallback |
| Database outage | API and dashboard readiness returned 503; no synthetic runs substituted; reconnection succeeded |
| Offline SDK | Queue bound 4, batch bound 2; 20 submitted events were accounted as dropped, 0 exported, 6 failed attempts; exporter terminated |
| Real SDK → API | Calculator result 29; 1 live completed run, 3 nested spans, 4 exported events, 0 drops, 1 intentionally lost acknowledgement/retry |
| Metrics / dashboard charts | Agent/run/span/tool counts agree; 100% success, 0 tokens, cost unavailable; chart totals and authenticated proxy match |
| Replay | Identical telemetry replay accepted 0 new events before and after restart |
| Browser | All 3 tests passed in about 69 s: synthetic workflow, one-time key lifecycle, restart/reconnection |
| Recovery | Explicit approval and separate execution; pending observation window; verification after at least 15 s; follow-up started after intervention |
| Restart persistence | Same volume; every row checksum matched across all 12 tables |
| Duplicate actions | Repeated approval and execution preserved the remediation, follow-up and audit history; exactly 1 approval/execution/recovery audit each |
| Browser reconnect | SSE opens 1 → 2, refreshes 1 → 3 after a full stack restart; no page reload or mutation replay |
| Shutdown | With an open browser: 13.94 s for the whole stack; final idle stop: 0.86 s. API/web exited 143 after confirmed teardown; PostgreSQL exited 0. No OOM/exit 137 |
| Secrets | 0 generated credential values in own logs/image metadata; build CA and native state absent from runtime images; project test keys revoked |

The database was retained with 3 projects, 5 agents, 27 runs, 111 spans, 112 deduplicated telemetry events, 1 anomaly/incident/investigation/remediation, 1 settings record, 2 revoked keys and 12 audit records. The restart comparison had 11 audits; intentional SDK key revocation added the twelfth afterward.

## Runtime configuration verified by Docker inspection

| Service | User | Memory limit | CPU limit | PID limit | Published host port |
| --- | --- | --- | --- | --- | --- |
| API | 10001:10001 | 512 MiB | 1 | 128 | 127.0.0.1:18002 |
| Web | 10001:10001 | 384 MiB | 1 | 128 | 127.0.0.1:13002 |
| PostgreSQL | postgres (UID 70) | 512 MiB | 1 | 128 | none |

API/web roots are read-only, capabilities are dropped, and privilege escalation is disabled. Limits are configured and inspected bounds, not a claim about peak memory consumption. Native tools were Python 3.12.14 and Node 24.19.0; image runtimes are pinned Python 3.12.12 and Node 24.14.0. Docker was 28.4.0, Compose 2.40.3, storage driver `vfs`.

Final image IDs:

- API: `sha256:ab3c0a511dd419e2331d44ea18910850cab1b5ac7b94f69c15c08a790f803c1c`
- Web: `sha256:e1f9bf11b1137b607480f3f734d14d8b155f9c7f230ff0cb74742680b8ff629e`
- PostgreSQL: `sha256:79bd7c99e923138f136f8009d6bffa66e21e9d4fda5c0c561b00fc9c90cfe537`

## Defects fixed and failed attempts

The first start failed because private host source permissions were copied into images and unreadable to their new non-root users. Image copy ownership and directory permissions are now explicit. The failed disposable database was retained; it was not reset to obtain a passing result.

An open SSE proxy made Next wait indefinitely during reverse-order Compose shutdown, causing exit 137 at the 30-second budget. Proxy streams now abort and close on SIGTERM; the API drains SSE and the current durable-worker transaction. Acceptance recognizes Uvicorn/Next's intentional SIGTERM exit 143 only with teardown evidence from the current process.

The restart browser regression initially failed because HTTP errors could permanently close EventSource. The client now recreates the stream with bounded backoff and refreshes persisted data on reconnect. Its successful regression remained part of the final full run.

SDK queue size zero previously created an unbounded queue, events could enqueue after shutdown, and a timed-out close gave no outcome. Positive bounds, a shutdown deadline, dropped-event accounting and a Boolean close result now expose that lifecycle. Persisted investigation phases are skipped on resume, and failed retries reset progress/report consistently, preventing completed checkpoints/audits from being replayed. The existing execution compare-and-set and post-intervention timestamp fix remain intact and are asserted by native and container/browser checks.

## Preservation and environment limitations

Every record checksum in the saved native SQLite database matched before/after acceptance, including its 130 runs, 541 spans, 542 events, 4 investigations, 4 settings records and 45 audits. The native admin token checksum also matched. Native SQLite was never passed to destructive tests; native `.next` was not used for production builds. No native service was stopped or restarted by acceptance. Native development servers were not listening at final inspection; they were not relaunched for this container increment.

The original PostgreSQL image ID remained unchanged. The pre-existing anonymous volume `5db08d25dae3dfa0bcb532f16df268d9e317afa7d5504b1645d932156dcd753f` remained present. All created application containers are stopped; all created PostgreSQL volumes remain. The earlier pilot and failed acceptance artifacts are retained for review.

Docker's default Buildx state path was read-only; a workspace-local `BUILDX_CONFIG` resolved it without changing registry configuration. Repeated `vfs` builds exhausted the 32 GiB disk. Only generated native build copies and six explicitly inspected cache records from this task's obsolete web builds were removed. No image, database volume or unrelated cache was pruned. The final full run completed; no requested local check remains blocked by Docker.

Hosted CI execution, rootless/custom Docker sockets, non-Linux/ARM browser execution, distributed/multi-worker coordination and live external LLM access are unverified. Native unit tests in this increment ran on temporary SQLite; container integration tested PostgreSQL. Real-agent intervention stays recommendation-only. No external ingress, credential rotation or host security change was made.

## Changed files

| Area | Files |
| --- | --- |
| Containers | `docker-compose.yml`, `.dockerignore`, `infrastructure/docker/api.Dockerfile`, `api_start.py`, `api_server.py`, `api_health.py`, `web.Dockerfile`, `web_start.mjs`, `web_health.mjs` |
| API/storage | `apps/api/app/config.py`, `db.py`, `main.py`, `services.py`, `apps/api/alembic/versions/001_initial.py`, `apps/api/requirements.txt`, `apps/api/tests/test_lifecycle.py` |
| SDK | `packages/python-sdk/agentscope_sdk/__init__.py`, `packages/python-sdk/pyproject.toml` |
| Web/lifecycle/browser | `apps/web/app/api/[...path]/route.ts`, `apps/web/components/workspace.tsx`, `apps/web/proxy.ts`, `apps/web/playwright.config.ts`, `apps/web/tests/e2e/workflow.spec.ts`, `container.spec.ts` |
| Acceptance/CI | `scripts/container_acceptance.py`, `package.json`, `.github/workflows/ci.yml`, `.gitignore` |
| Documentation/evidence | `README.md`, `docs/local-containers.md`, `docs/container-validation.md`, `docs/validation/local-container-acceptance.json` |

Review the feature patch against the preserved baseline with `git diff 89356ca..feat/local-container-acceptance`. The validation-record commit adds documentation and measured evidence after the tested implementation commit; it does not change application code.
