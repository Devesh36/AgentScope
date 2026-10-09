# AgentScope

Agent observability and evidence-grounded incident response. A dark-first Next.js dashboard backed by authenticated FastAPI APIs and persistent telemetry—not a static prototype.

## Run locally

Requires Python 3.12+, Node.js 22+, and [uv](https://docs.astral.sh/uv/).

```bash
npm run setup
npm run dev
```

The dashboard listens on port **3000** and the API on **8000**. The default local mode uses SQLite with WAL, a durable transactional database outbox, and a bounded deterministic LangGraph investigator. It requires no model credentials, Redis, or external agent services. PostgreSQL is supported through `DATABASE_URL` and Alembic migrations.

**A new workspace starts empty.** Use Settings → API keys to create a project key, register an agent, and emit actual telemetry. Simulation lab explicitly generates **synthetic demo telemetry**; demo agents, runs, and investigation reports are labeled throughout. Overview and Run explorer can filter live telemetry and demo data separately. Simulations are never started automatically.

### What is implemented

- Overview with query-backed agent/run/incident metrics, model-priced estimated cost, token charts, tool error trends, health, and investigations. Unknown pricing is displayed as unavailable.
- Agent registration, configuration, health, recent runs and incidents.
- Filterable and paginated run explorer with nested trace waterfall, tool timeline, LLM details, error events, token breakdown, and metadata.
- Incident center with search, filtering, ordering, investigations, detection evidence, remediation history, and recovery results.
- Persisted investigation workspace: evidence references, execution timelines, qualitative hypotheses, contradictory evidence, recommendations, and decision summaries. Hidden chain-of-thought is never requested or displayed.
- Settings for projects, one-time API key creation/revocation, agent workflow constraints, five configurable detectors, model provider configuration, remediation policy, and enforced telemetry retention.
- Reproducible simulation scenarios for tool loops, token budgets, tool failure storms, stalls, unexpected tools, and healthy execution.
- All requested section-15 endpoints, JSON and protobuf OTLP trace ingestion, project authorization, batch validation, payload limits, ingestion deduplication, durable background processing, authenticated SSE, health checks, and Prometheus counters.
- An installable metadata-first Python SDK with sync/async decorators, nested context, LLM usage recording, progress events, bounded export queues, retries, and graceful shutdown.

## Instrument an agent

The setup script installs the local SDK. API keys are shown once in Settings and only their digests are stored.

```python
from agentscope_sdk import AgentScope

scope = AgentScope(
    endpoint="http://localhost:8000",
    api_key="YOUR_PROJECT_API_KEY",
    agent_name="research-agent",
    framework="LangGraph",
)

@scope.trace_tool
async def search(query):
    return await your_search(query)

@scope.trace_agent
async def run_agent(task):
    results = await search(task)
    scope.heartbeat("search complete")
    return results

# When instrumenting an actual LLM call, populate observed usage, never estimates:
# with scope.llm("generate", model="gpt-4.1-mini") as usage:
#     response = client.call(...)
#     usage["input_tokens"] = response.usage.input_tokens
#     usage["output_tokens"] = response.usage.output_tokens

# Close on application shutdown; do not block an async event loop:
# await asyncio.to_thread(scope.close)
```

Run the real local calculator example with `AGENTSCOPE_API_KEY` set securely:

```bash
.venv/bin/python examples/demo-agent/main.py
```

The SDK exports on a background thread. It records argument/result fingerprints and exception classes instead of raw arguments, prompts, responses, or exception text. A failed export cannot interrupt agent execution; counters distinguish exported, dropped, and failed exports. No paid model is used by the example.

## API

Interactive OpenAPI documentation is served by FastAPI at `/docs`. See [the API guide](docs/api.md) for authentication and event examples. SDK/project requests use `Authorization: Bearer <project-api-key>`. Dashboard administration uses a server-only token; it is never included in client JavaScript. `X-Project-ID` is required for dashboard project-scoped requests. Resource lookups enforce project ownership and keys cannot cross project boundaries.

SSE at `/api/v1/events` announces project-scoped refreshes and always triggers a complete refresh after reconnect. Polling provides a fallback. Telemetry events and outbox entries share a database transaction. The local worker marks an outbox event processed in the same transaction as anomaly/incident creation. A restart retries unfinished work without duplicate incidents. **Run a single API worker in local mode.**

## Investigations and remediation

Deterministic detection and investigation work without an external model. The LangGraph workflow persists every checkpoint, limits graph execution to eight steps, and references stored spans. Optional OpenAI-compatible suggestions use a server-side `AGENTSCOPE_LLM_API_KEY`, an HTTPS destination allowlist, a ten-second timeout, and a 600-token output bound. Set `AGENTSCOPE_LLM_ALLOWED_HOSTS` to the intended provider hostname, enable the destination in your environment network policy, and select the provider in Settings. Invalid or unavailable output falls back to the deterministic report. Model suggestions remain **unverified**; deterministic findings remain primary. Live paid-provider access has not been validated.

Real agents remain **recommendation-only**: telemetry does not confer control. This release registers only an isolated synthetic demo control adapter. To practice intervention, enable **Allow isolated demo control** in Settings → Remediation policies, approve a proposal, then execute it separately. The simulation adapter cancels its recorded demo execution and emits clearly labeled successful follow-up telemetry. Recovery is checked after a 15-second observation window against actual persisted follow-up runs. Approval, execution, and measurements are audited. An action response does not resolve an incident by itself.

## Storage and security

Local data and the generated dashboard token live in ignored `.local/`. Do not commit it. Set `DASHBOARD_PASSWORD` to protect dashboard pages and its privileged API proxy before exposing the web server beyond a trusted local environment. Use HTTPS and an authenticated ingress for deployment. The API binds to loopback in the development script; project API keys can access it directly. The web proxy rejects cross-origin mutation requests.

`DATABASE_URL=postgresql+psycopg://...` enables PostgreSQL. All identifiers use UUIDs except preserved OTel trace/span identifiers. Foreign keys, indexes, project constraints, event deduplication, and Alembic migrations are provided. Retention removes expired executions without incidents once per hour; evidence linked to incidents stays pinned. Model list pricing is versioned in `apps/api/app/telemetry.py`; unknown models remain unpriced.

## Verification

```bash
npm run test:api                     # API + SDK tests; isolated temporary database
npm run test:web                     # Vitest presentation/trace tests
npm --prefix apps/web run typecheck
.venv/bin/ruff check apps/api packages/python-sdk examples
.venv/bin/mypy apps/api/app --ignore-missing-imports --follow-untyped-imports
npm run build
# While npm run dev is running:
npm --prefix apps/web run test:e2e
```

Playwright uses Chromium from the locked `@sparticuz/chromium` npm package, avoiding an extra browser CDN requirement. Browser checks create a dedicated project and labeled demo telemetry; they cover empty states, simulation, investigation, approval, delayed recovery, API key lifecycle, and mobile navigation. Screenshots are generated in ignored `.local/`.

## Scope

This release implements the requested dashboard and REST API with a functional local telemetry/incident pipeline. It is a modular monolith, not the complete production infrastructure described in the broader project vision. Multi-user organizations/RBAC, Redis Streams dispatch and dead-letter queues, collector deployment, distributed worker coordination, custom real-agent control adapters, cancellable model investigations, and ClickHouse are future extensions. The current SDK exports normalized JSON; the API separately accepts OTel protobuf/JSON from standard exporters. Neither Docker deployment nor external model credentials are required for local development.

## Optional Docker stack

`docker-compose.yml` builds the web/API containers and runs PostgreSQL. Export a strong URL-safe `POSTGRES_PASSWORD` securely, then run `docker compose up --build`. Published ports bind to loopback; add an authenticated HTTPS ingress before remote access. Set `DASHBOARD_PASSWORD` for dashboard authentication. No credential is embedded in the repository. The compose stack uses the same durable local outbox; Redis dispatch is not included in this release.
