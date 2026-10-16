# AgentScope

**Understand your agents, from execution to recovery.**

AgentScope is a self-hosted observability workspace for AI agents. It brings together execution traces, tool calls, model usage, incident detection, and evidence-grounded investigations so you can understand what happened and decide what to do next.

Local monitoring runs without a model API key. The conversational REPL requires a configured assistant model: a provider API, a local model, or an authenticated Codex/Claude CLI. Start the server, connect the Python SDK or interactive CLI, and inspect the same persisted records in the dashboard.

[Getting started](#getting-started) · [CLI guide](docs/cli.md) · [API reference](docs/api.md) · [Container guide](docs/local-containers.md) · [Development](#development)

## What AgentScope does

| Capability | How it helps |
| --- | --- |
| Execution visibility | Inspect nested agent, tool, and LLM spans, latency, failures, observed token usage, and estimated cost for supported models. |
| Incident detection | Identify repeated tool calls, token-budget overruns, tool failure storms, stalled executions, and unexpected workflow steps. |
| Evidence-grounded investigation | Review persisted findings, competing hypotheses, recommendations, and references to the spans behind them. |
| Controlled demo intervention | Approve a proposal, execute it separately, and verify recovery against recorded follow-up telemetry. |
| Project-scoped telemetry | Create and revoke ingestion API keys, separate live runs from synthetic demos, and configure detectors and retention. |
| Multiple interfaces | Use the Next.js dashboard, interactive Python CLI, Python SDK, or authenticated REST and OTLP ingestion APIs. |

**Real agents remain recommendation-only.** Executable remediation is limited to an explicitly enabled, isolated synthetic demo adapter. A successful action response alone does not establish recovery.

## Getting started

### Prerequisites

- Python **3.12+**
- Node.js **24.x** and npm, matching the CI toolchain
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Git

Docker, PostgreSQL, Redis, and external model credentials are not required for native development.

### Configure and meet your assistant

```bash
uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
agentscope configure
cd /path/to/your/project
agentscope repl
```

Setup guides you through AgentScope's assistant provider, model, and hidden credential entry. The REPL opens directly at the command prompt; type `watch` to launch the local dashboard without configuring chat. Run `configure` only when you want assistant chat. Inside the REPL, type `model check`, then **Who are you?** or **What does AgentScope do?** to receive an answer from your chosen model. Conversation history supports follow-up questions.

Supported options include OpenAI/Codex, Anthropic/Claude, Gemini, OpenRouter, Groq, DeepSeek, Ollama, compatible endpoints, and existing Codex/Claude CLI logins. Use `model list`, `model use PROFILE`, and `chat reset` to manage the session. The assistant model is separate from your application's models; project summaries are shared only after `context on`. See [the chat and provider guide](docs/chat.md).

### Monitor your existing project

On macOS or Linux, install the CLI with uv, then run it from your application directory. The local dashboard requires Python 3.12+, Node.js 24 with npm, and uv. Homebrew installs these prerequisites automatically; see the [CLI guide](docs/cli.md).

```bash
uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
cd /path/to/your/project
agentscope watch -- python app.py
# For a Node.js application:
# agentscope watch -- npm start
```

AgentScope starts a loopback-only API and dashboard, creates a project and ingestion key, opens the correct project in your browser, and captures supported LLM activity while your application runs. The first installed run prepares its bundled local services; subsequent runs reuse them. Activate your application's virtual environment before launching Python.

You can also use two terminals:

```bash
# Terminal 1, in your project:
agentscope watch
# Terminal 2, in the same project:
agentscope run -- python app.py
```

Or open `agentscope repl`, then type `watch` (or `monitor .`). Monitoring runs in the background while `status`, `incidents`, `investigate`, and `open` remain available. `stop` stops the local watch session. The CLI watcher stays available after a short-lived application finishes; Ctrl+C stops its services. Saved records are restored when you watch the same directory again.

**Automatic capture:** Python OpenAI chat completions/Responses and Anthropic Messages (`create`, synchronous/asynchronous, including `stream=True`); Node.js fetch-based OpenAI/Anthropic-compatible endpoints, including streamed responses. Existing processes need to be relaunched through `watch`/`run`. Custom fetch implementations, unsupported providers/languages, and tool or whole-agent boundaries need SDK/OTLP instrumentation. Python can use `AgentScope.from_watch()` to group calls into agent/tool traces.

The dashboard displays live LLM calls, failures, latency, tokens, estimated cost, and incidents. Prompt/response content and provider credentials are excluded from automatic telemetry. **Unsupported claims remain “Not evaluated”** until an application supplies a reference-based assessment using `scope.record_grounding(...)`; this is not an automatic hallucination detector. Missing provider usage keeps cost unavailable.

Watch data and credentials are stored outside your repository in `~/.agentscope/`, with `AGENTSCOPE_HOME` available for an alternative location. No source files or dependency manifests in your project are changed. Read the [watch guide](docs/watch.md) for options and supported integrations.

### Run the local workspace from source

```bash
git clone --branch main https://github.com/Devesh36/AgentScope.git
cd AgentScope
npm run setup
npm run dev
```

Setup creates a Python virtual environment, installs the API, SDK, and CLI, installs locked web dependencies, and runs database migrations. Keep the development process running while using the dashboard or CLI.

| Interface | Local address |
| --- | --- |
| Landing page | `http://localhost:3000` |
| Product documentation | `http://localhost:3000/docs` |
| Dashboard | `http://localhost:3000/dashboard` |
| API | `http://127.0.0.1:8000` |
| Interactive API schema | `http://127.0.0.1:8000/docs` |

A new workspace starts empty. In the dashboard, create a project and an API key in **Settings**, then instrument your agent. To explore first, use the explicitly labeled synthetic demo below.

### Connect the CLI

From the repository root, open another terminal:

```bash
.venv/bin/agentscope repl \
  --url http://127.0.0.1:8000 \
  --dashboard http://127.0.0.1:3000 \
  --token-file .local/admin-token
```

The CLI uses the server's admin token file. Project ingestion API keys are for the SDK and telemetry APIs; they do not replace this admin credential. Do not commit or share token files.

To install the CLI separately with uv:

```bash
uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
agentscope --version
agentscope repl --token-file /path/to/server/admin-token
```

`watch` starts its own local workspace. `repl --url ... --token-file ...` also supports connecting to an existing server. Homebrew installation and connection options are covered in the [CLI guide](docs/cli.md).

The REPL provides grouped help, an offline `guide`, project-aware prompts, and
readable summaries with `status`, `agents`, `runs`, and `incidents`. Slash commands
such as `/help` are supported; add `--json` to inspection commands for full API
data. See the [interactive workspace guide](docs/cli.md#interactive-workspace).

### Explore a synthetic incident

In the REPL:

```text
help
status
demo
```

`demo` creates a dedicated project, records synthetic runs, detects a tool-loop incident, and waits for its investigation. It prints the recommendation, evidence count, and proposal ID. It does not approve or execute an action.

![Captured AgentScope CLI session showing a synthetic tool-loop incident, completed investigation, eight evidence references, and a proposal awaiting approval.](apps/landing/public/docs-assets/cli-demo.png)

*Captured from a local CLI session against the running API. IDs are specific to that session; use the IDs printed by your own run.*

To practice the separate intervention steps, replace the placeholders with your proposal and investigation IDs:

```text
policy demo on
approve REMEDIATION_ID
execute REMEDIATION_ID
verify INVESTIGATION_ID
```

Verification observes persisted follow-up runs after a 15-second window. Select the demo project in the dashboard to inspect the same traces, incident, and investigation. See the [CLI guide](docs/cli.md) for other scenarios and command details.

## Instrument your Python agent

The setup script installs the local `agentscope-sdk`. Create a project ingestion key in **Settings → API keys** and supply it through your application's secret configuration as `AGENTSCOPE_API_KEY`.

```python
import os
from agentscope_sdk import AgentScope

with AgentScope(
    endpoint="http://127.0.0.1:8000",
    api_key=os.environ["AGENTSCOPE_API_KEY"],
    agent_name="calculator-agent",
) as scope:

    @scope.trace_tool
    def add(left, right):
        return left + right

    @scope.trace_agent
    def run():
        total = add(2, 3)
        scope.heartbeat("calculation complete")
        return total

    print(run())
```

The SDK registers the agent and exports telemetry on a bounded background queue. It supports synchronous and asynchronous decorators, nested spans, progress events, retry deduplication, and graceful shutdown. Arguments and results are represented by fingerprints rather than raw payloads. Record actual model usage when instrumenting LLM calls; unknown model pricing remains unavailable.

For a runnable async example, see [examples/demo-agent/main.py](examples/demo-agent/main.py). With the project API key configured securely, run `.venv/bin/python examples/demo-agent/main.py`.

## Architecture and configuration

AgentScope is a modular monolith: a **Next.js** dashboard proxies authenticated requests to a **FastAPI** API, while **SQLAlchemy** stores telemetry and a durable transactional outbox. The local worker processes detections and a bounded, deterministic **LangGraph** investigator.

Native mode uses SQLite with WAL and stores data and the generated admin token in ignored `.local/`. Run one API worker in local mode. PostgreSQL is supported through `DATABASE_URL` and Alembic migrations.

- Set `DASHBOARD_PASSWORD` before making the workspace available outside a trusted local environment. Use HTTPS and authenticated ingress for deployment.
- Keep the admin token, ingestion API keys, and `.local/` private. Project API keys are stored as digests and can be revoked.
- Optional OpenAI-compatible suggestions require a server-side provider key and an HTTPS destination allowlist. The deterministic investigator works independently, and model suggestions remain unverified.
- The optional [container stack](docs/local-containers.md) uses PostgreSQL, pinned images, mounted secrets, readiness checks, and loopback-only published ports.

The current release does not provide multi-user organization management, production RBAC, distributed worker coordination, or control adapters for real agents. External paid-provider behavior and production deployments require separate validation.

## Development

Development follows a [prioritized roadmap and engineering baseline](docs/continuous-development.md).
GitHub Actions validates every change and runs scheduled checks daily at 03:30 UTC
(09:00 India time), with additional container and Homebrew checks on Monday.
The schedule monitors quality; recurring AI implementation needs a connected task runner.

The run explorer and incident center support shareable view URLs. Use **Copy view
link** to preserve the project, search, filters, and page; opening the link still
requires access to that workspace. Dropdowns and pagination support browser
Back/Forward, and searches wait briefly while you type. **Reset filters** clears
the explorer search/status/severity/sort and returns to its first page; the run
explorer retains the selected project, telemetry source, and time range.

Use the existing repository scripts:

```bash
npm run test:api
npm run test:cli
npm run test:web
npm run accept:performance -- --report .local/performance-report.json
npm --prefix apps/web run typecheck
.venv/bin/ruff check apps/api packages/python-sdk packages/cli examples
.venv/bin/mypy apps/api/app --ignore-missing-imports --follow-untyped-imports
npm run build
```

With the local servers running, `npm --prefix apps/web run test:e2e` exercises the browser workflow. Browser tests create dedicated synthetic projects. Stop the web development server before a production build so the build does not replace its active output.

`npm run accept:containers` runs the isolated container, SDK, browser, CLI, restart-persistence, and graceful-shutdown checks. Read its [prerequisites and resource requirements](docs/local-containers.md) first. It retains its database volume and sanitized measurements; it does not prune Docker resources.

### Performance

The 0.3.2 optimization pass batches telemetry ingestion, summarizes history in SQL, and loads dashboard features per page. In a local 5,000-run SQLite fixture, overview reads fell from 314 ms to 56 ms; 500-event updates fell from 603 ms to 78 ms. The dashboard uses live events for refreshes and polls when disconnected. See [the measured results and reproduction steps](docs/performance.md).

### Landing site and documentation

`apps/landing` is the independent, light-and-amber public site. It exports the homepage and `/docs` as static files and requires no API, database, or server credentials.

```bash
npm --prefix apps/landing ci
npm --prefix apps/landing run build
npm --prefix apps/landing run typecheck
npm --prefix apps/landing run verify
```

The public documentation includes a **Terminal tour** with ten real session captures, full-size images, and a downloadable PDF. It covers model setup, chat, monitoring, usage, investigations, synthetic recovery, and shutdown.

The homepage’s **Phase** section records dated development milestones and every source commit. Its build merges Git history with a curated snapshot, preserving older milestones in shallow or Git-free builds. See [the timeline maintenance guide](docs/development-phases.md) when making changes.

For Vercel, use **apps/landing** as the Root Directory and **main** as the production branch. See [the deployment guide](apps/landing/README.md). The dashboard remains in `apps/web`; it is a separate application.

## Documentation

- **Public `/docs` page:** product overview, local setup, CLI walkthrough, terminal screenshots, SDK integration, and troubleshooting.
- [Chat guide](docs/chat.md): assistant setup, supported providers, model profiles, and optional project context.
- [Watch guide](docs/watch.md): automatic local startup, supported runtime capture, persistence, and grounding checks.
- [CLI guide](docs/cli.md): installation, authentication, scenarios, and explicit intervention commands.
- [API reference](docs/api.md): endpoints, project authorization, normalized events, and OTLP ingestion.
- [Container guide](docs/local-containers.md): prerequisites, startup, restart, shutdown, and trust configuration.
- [Performance guide](docs/performance.md): measured optimizations, reproducible benchmarks, and scaling limits.
- [Continuous development](docs/continuous-development.md): scheduled quality checks, release discipline, engineering baseline, and prioritized milestones.
- [Local validation records](docs/container-validation.md): measured behavior and remaining limitations.

For a reproducible bug report, include the source commit, runtime versions, steps to reproduce, and sanitized output. Exclude credentials, private telemetry, and `.local/` contents.
