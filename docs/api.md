# API v1

FastAPI `/docs` and `/openapi.json` describe the complete live schema. API keys are generated through Settings, hashed at rest, project-scoped, and immediately revocable. All business endpoints require authentication. Liveness/readiness expose no telemetry.

| Area | Endpoints |
|---|---|
| Projects (dashboard admin) | `POST /api/v1/projects`, `GET /api/v1/projects` |
| Agents | `POST /api/v1/agents`, `GET /api/v1/agents`, `GET /api/v1/agents/{id}`, `PATCH /api/v1/agents/{id}` |
| Telemetry | `POST /api/v1/telemetry/events`, `POST /v1/traces` |
| Runs | `GET /api/v1/runs`, `GET /api/v1/runs/{id}`, `GET /api/v1/runs/{id}/trace` |
| Anomalies | `GET /api/v1/anomalies` |
| Incidents | `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}`, `POST /api/v1/incidents/{id}/investigate` |
| Investigations | `GET /api/v1/investigations`, `GET /api/v1/investigations/{id}` |
| Remediation (dashboard admin) | `POST /api/v1/remediations/{id}/approve`, `POST /api/v1/remediations/{id}/execute` |
| Metrics | `GET /api/v1/metrics/overview`, `GET /metrics` (admin) |
| Live refresh | `GET /api/v1/events` |
| Settings | `GET /api/v1/settings`, `PUT /api/v1/settings`, `GET /api/v1/settings/provider-status` |
| API keys (dashboard admin) | `GET /api/v1/api-keys`, `POST /api/v1/api-keys`, `DELETE /api/v1/api-keys/{id}` |
| Synthetic scenarios (dashboard admin) | `POST /api/v1/simulations` |
| Health | `GET /health/live`, `GET /health/ready` |

Run queries accept `search`, `status`, `hours`, `synthetic`, `limit` and `offset`. Incident queries accept `search`, `status` (`active` selects unresolved incidents), `severity`, `sort` (`newest` or `oldest`), `limit` and `offset`. List responses for runs/incidents return `{items, total}`. Metrics and runs accept `synthetic=true/false` to distinguish demo and live data. All times are timezone-aware ISO 8601.

## Normalized event

After registering an agent, send a batch with its returned UUID. Identical `event_id` values are deduplicated within the project. Different events may update the same span as it starts/ends; older updates do not reopen a terminal span. Parent spans may arrive after their children.

```json
{
  "events": [{
    "event_id": "stable-export-id-1",
    "agent_id": "REGISTERED_AGENT_UUID",
    "run_id": "your-execution-id",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "span_id": "0123456789abcdef",
    "parent_span_id": null,
    "name": "research task",
    "kind": "agent",
    "status": "completed",
    "started_at": "2026-10-09T12:00:00Z",
    "ended_at": "2026-10-09T12:00:02Z",
    "attributes": {}
  }]
}
```

Maximum 1,000 events and 2 MiB per request. Timestamps over five minutes in the future are rejected. LLM events may specify `model`, `input_tokens`, and `output_tokens`; list pricing is applied only to known model versions. Tool events may include `argument_fingerprint`, `result_fingerprint`, and `legitimate_polling` in `attributes`. Do not send secrets, raw prompts, or raw tool outputs.

OTLP `/v1/traces` accepts `application/x-protobuf` or standard OTLP JSON. Supply `X-Agent-ID` with a registered agent UUID and your project API key. Resource/span attributes include `agentscope.run_id`, `agentscope.kind`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, and `gen_ai.usage.output_tokens`. Trace IDs and span IDs are preserved.

Approval and execution are separate endpoints. Execution rejects unapproved proposals, unsupported adapters, and disabled demo-control policy. No API can control an unregistered real agent. Retrying an already executed action returns the existing recorded result.
