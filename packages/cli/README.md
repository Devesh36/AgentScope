# AgentScope CLI

Install local agent observability into your workflow:

```bash
uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
cd /path/to/your/project
agentscope watch -- python app.py
# Or: agentscope watch -- npm start
```

On macOS/Linux, watch starts its bundled API and dashboard, provisions project-scoped ingestion, and opens the local dashboard. Python 3.12+, Node.js 24 with npm, and uv are required. The first run prepares service dependencies; later runs reuse them. Your application keeps its existing environment and dependencies.

`agentscope watch` can run independently; launch your app from another terminal with `agentscope run -- YOUR_COMMAND`. In `agentscope repl`, type `watch` or `monitor .`, then inspect the project with `status`, `incidents`, and `open`. Use `stop` or `exit` to stop REPL monitoring.

Automatic metadata capture supports Python OpenAI/Anthropic create calls and Node.js fetch-based compatible endpoints, including streams. Unsupported integrations and tool boundaries use SDK/OTLP instrumentation. Existing processes must be relaunched through watch/run. No prompt or response content is exported automatically, and factual accuracy remains unassessed until an application submits an explicit grounding evaluation.

The CLI also connects to existing AgentScope servers and provides synthetic incident demos with separate policy, approval, execution, and verification controls.

See [the watch guide](https://github.com/Devesh36/AgentScope/blob/main/docs/watch.md) and [CLI reference](https://github.com/Devesh36/AgentScope/blob/main/docs/cli.md).
