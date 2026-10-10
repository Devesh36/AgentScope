# Monitor an existing project

AgentScope 0.4.0 provides a local monitoring workflow on **macOS and Linux**.
The application runs in its own environment. AgentScope launches local services
and captures supported runtime calls without editing the application repository.

## Install and start

With Python 3.12+, Node.js 24 with npm, and uv installed:

```bash
uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
cd /path/to/your/project
# Activate the project's Python environment first, if it has one.
agentscope watch -- python app.py
# Or, for a Node.js application:
agentscope watch -- npm start
```

The first run prepares the bundled FastAPI and Next.js services in a private user
directory. This requires network access to install their locked dependencies.
Later sessions reuse the prepared runtime. The CLI itself has no provider SDK
dependencies: your application supplies its existing OpenAI/Anthropic client.

Watch provisions a stable project, a private ingestion key, and a real telemetry
agent. It binds the API and dashboard to `127.0.0.1`, prints a dashboard URL, and
opens the correct project automatically. Ports 8000 and 3000 are preferred; busy
ports are skipped rather than taking over another service.

The CLI remains running after a short application finishes, allowing inspection
and subsequent launches. Ctrl+C stops its services and launched application.
`--once` instead stops when the launched application exits and preserves its exit
code. Records remain available the next time you watch the same directory.
Unfinished observations are marked **interrupted** when monitoring stops; this
does not assert that the application failed or that a business action was cancelled.
Later terminal telemetry can still provide the actual outcome.

## Separate watcher and application

```bash
# Terminal 1, inside the project:
agentscope watch
# Terminal 2, inside the same project:
agentscope run -- python app.py
```

`run` connects only to a currently running watcher for that project. Both commands
accept `--repo DIRECTORY`. Watch also accepts a directory as its first positional
argument. Put application commands after `--`; commands are passed directly to the
operating system without shell evaluation.

## Interactive monitoring

Configure AgentScope's own chat model with `agentscope configure` before chatting. The first interactive REPL offers setup automatically. This configuration is separate from your application's LLM credentials. You can ask **Who are you?** or discuss summary metrics after `context on`; see [the chat guide](chat.md). Monitoring itself remains available without a chat provider.

```text
agentscope repl
agentscope> watch
agentscope> status
agentscope> incidents
agentscope> open
agentscope> stop
```

Inside the REPL, `monitor .` is an alias for `watch`. Monitoring runs in the
background, and the REPL selects the provisioned project automatically. Use
`investigate INCIDENT_ID` to collect a persisted investigation. `stop`, `exit`,
or EOF stops that REPL's watcher. A separate terminal can use `agentscope run`
while the REPL remains interactive. Existing-server REPL connections remain
supported through `--url`, `--dashboard`, and `--token-file`.

## Automatic capture coverage

| Application integration | Captured activity |
| --- | --- |
| Python OpenAI | `chat.completions.create` and `responses.create`, sync and async, including `stream=True`. |
| Python Anthropic | `messages.create`, sync and async, including `stream=True`. |
| Node.js | Global-fetch POST calls to paths ending in `/chat/completions`, `/responses`, or `/messages`, including SSE streams. This covers provider SDKs using global fetch. |
| Python SDK | Optional whole-agent and tool spans, nested automatic LLM spans, progress, and explicit grounding evaluations. |
| Other integrations | Use the existing authenticated normalized-event or OTLP ingestion API. |

Already-running processes must be relaunched through watch/run. Python isolated
mode (`-I`, `-S`), custom import loaders, Python SDK streaming helper methods such
as `messages.stream`, Node clients replacing global fetch or using native HTTP,
and unsupported providers/languages require manual instrumentation. Watch does
not infer executions by reading source files or scanning arbitrary system traffic.

Automatic capture records provider/operation/model, timing, status, and reported
input/output token counts. Errors contain exception classes or HTTP status codes,
not response bodies. Prompt text, generated text, tools' arguments, request
headers, and provider credentials are excluded. No global monkey patches or
dependency changes are installed into the user's project: hooks are scoped to
processes explicitly launched through watch/run.

Each automatically captured provider call becomes a run with a nested LLM span.
For a whole-agent trace with tool boundaries, use the Python SDK:

```python
from agentscope_sdk import AgentScope

scope = AgentScope.from_watch()

@scope.trace_tool
def search_records(query):
    return lookup(query)  # Your existing application function.

@scope.trace_agent
def execute_agent():
    records = search_records("example")
    # Supported provider calls here are captured as children of this agent run.
    return your_existing_agent(records)

try:
    execute_agent()
finally:
    scope.close()
```

Launch that application through watch/run. Custom tool arguments/results are
fingerprinted by the SDK. Automatic LLM capture alone cannot detect tool loops
without instrumented tool spans. Existing deterministic detectors continue to
operate on the recorded spans and configured thresholds.

## Factual accuracy and grounding

The dashboard shows **Not evaluated** until your application submits an explicit
grounding assessment. It does not label outputs as hallucinations from usage
metadata alone. An application with reference information can record its own check:

```python
with scope.span("agent", "agent"):
    with scope.llm("answer", "gpt-4o-mini") as usage:
        answer = generate_answer()
        unsupported = evaluate_against_references(answer)
        scope.record_grounding(usage, unsupported, "reference-check")
```

The check's implementation and reliability belong to the application. Only the
unsupported-claim count and evaluator label are recorded. Evaluated calls and
unsupported claims appear separately from LLM execution failures. An explicit
LLM SDK span suppresses duplicate automatic capture for its provider call; fill
its usage fields from the provider response when recording token/cost metrics.

## Options and storage

```bash
agentscope watch --repo /path/to/project --no-open
agentscope watch --port 3100 --api-port 8100 -- npm start
agentscope watch --once -- python batch_job.py
```

State is stored under `~/.agentscope/`, keyed by the resolved project directory.
Set `AGENTSCOPE_HOME` to choose another location. Service setup, API, and dashboard
logs are local files; the application retains its own terminal output. The user
directory is private and credential files have mode 0600. No credentials are
placed on command lines or in dashboard URLs. The target process receives only
its ingestion connection, rather than the dashboard admin credential.

One watcher owns a project at a time. Owned service process groups are stopped
on normal shutdown; a small supervisor also terminates them if their parent
disappears. Watch sessions have server-side heartbeat expiry so an interrupted
session is not shown as live indefinitely.

If the dashboard is empty, confirm the app was launched through watch/run and
uses a supported integration. A waiting watcher is distinct from captured LLM
activity. Missing provider usage leaves estimated cost unavailable; for OpenAI
chat streams, request `stream_options={"include_usage": True}` if usage is needed.
Unsupported model pricing also remains unavailable.

## Local verification

```bash
npm run test:api
npm run test:cli
npm run build
npm run accept:watch
```

Watch acceptance exercises real provider SDKs against local mock endpoints;
it makes no paid model calls. See its output/report for the tested SDK versions
and covered behavior. Windows local service startup and unlisted provider paths
are not part of this release's automatic coverage.

See [the measured local validation](watch-validation.md) for the release checks.
