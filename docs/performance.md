# Performance and monitoring overhead

AgentScope 0.3.2 reduces database queries, dashboard loading size, and idle monitoring work. These measurements compare the previous release (`bb91a85`, CLI 0.3.1) with the optimization pass on October 10, 2026 (UTC), in the same cloud workspace.

## Measured API improvements

The SQLite read fixture contains 20 agents, 5,000 runs, and 5,000 LLM spans. Each time is the median of five calls to the API read function, including JSON serialization. Ingestion measures updates to 500 existing runs, including the database commit, after one warm-up batch. SELECT counts exclude writes, HTTP, and authentication.

| Operation | Before | After | SELECT queries before → after |
| --- | ---: | ---: | ---: |
| Overview | 314.04 ms | 56.17 ms | 150 → 16 |
| Agent list | 76.67 ms | 15.44 ms | 141 → 6 |
| 50-run page | 18.80 ms | 3.19 ms | 102 → 4 |
| 500-event updates | 602.65 ms | 77.72 ms | 2,501 → 5 |

Overview peak Python allocations fell from 18.54 MiB to 0.66 MiB in a separate `tracemalloc` pass. This measures Python allocations for that call, rather than total process memory. Totals, tokens, cost, failure counts, grounding assessments, and latency percentiles match the baseline fixture. Separate checks cover submillisecond durations and half-millisecond rounding ties on both databases.

History totals now use SQL aggregates. Agent previews load five runs and five incidents per agent; run pages load their related records in batches. Telemetry batches preload project-scoped agents, deduplication IDs, runs, and spans, then calculate affected run totals together. Migration `002` adds indexes for project/time filters, agent previews, incidents, and pending work, without rewriting telemetry.

## Dashboard and runtime

Fresh production pages in Chromium loaded these decoded JavaScript response sizes:

| Page | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Overview | 1,180,546 bytes | 923,873 bytes | 22% |
| Runs | 1,180,546 bytes | 601,834 bytes | 49% |

These are uncompressed response body sizes, rather than network transfer bytes. The number of JavaScript requests increased from 11 to 12 as the application split page features into separate bundles. Chart code loads with the overview rather than every dashboard page.

A connected dashboard refreshes through live events; the 15-second poll remains a fallback for disconnection. Hidden tabs close their event connection and reconnect when visible. Refresh bursts are coalesced, and superseded query requests can be cancelled. API authentication sessions close before event streaming, freeing database connections while a tab stays open.

The Node.js capture hook schedules its flush timer only when events are queued. Python watch capture reuses the already provisioned agent ID instead of registering again. Existing bounded queues, retry behavior, and shutdown flushing remain supported.

The overview health banner now reflects failed runs, failed LLM calls, and failed tool calls, including failures that have not generated a detector incident. Unsupported claims still require a supplied grounding evaluation; unknown model pricing remains unavailable.

## Reproduce

After `npm run setup`, run:

```bash
npm run accept:performance -- --report .local/performance-report.json
npm run test:api
npm run test:cli
npm run test:web
npm run accept:watch -- --browser
```

The performance runner creates and deletes a temporary SQLite fixture. It overrides its own database/data paths and does not connect to your configured database or inspect private project records. The report is optional and saved at the path you supply.

The 32 API/SDK tests passed on SQLite and an isolated PostgreSQL database. The 14 watch acceptance checks cover real OpenAI/Anthropic SDKs against local mock HTTP endpoints, streaming, exceptions, agent/tool grouping, grounding, investigations, persistence, REPL use, and shutdown. Browser checks verify live failure reporting without a manual refresh. Wheel and source-archive builds, a fresh installed runtime, and migration `002` passed.

A separate genuine local SmolLM2 inference was also captured through the REPL after upgrading the existing demo: three recorded LLM calls, one deliberately invalid-model failure, and 120 observed tokens. Previous demo data survived the migration. This local inference does not validate paid external providers.

The sanitized [measurement record](validation/performance-local.json) contains fixture data and validation results. Times vary by hardware, caching, and workload. Exact latency percentiles still load duration scalars for the selected window, so their memory use grows with its terminal-run count; agent lists still grow with the number of registered agents. These results measure the stated local fixture, rather than production capacity.
