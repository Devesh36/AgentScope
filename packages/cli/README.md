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

Configure AgentScope's assistant with `agentscope configure` before chatting. The REPL opens directly at the command prompt. Type `watch` for local monitoring without a chat model or provider key, or `configure` to set up optional assistant chat. Type **Who are you?**, **What does AgentScope do?**, or `chat MESSAGE` for answers through your selected OpenAI/Codex, Anthropic/Claude, Gemini, local, compatible, or CLI-backed model. Use `model list`, `model use PROFILE`, and `chat reset`. `context on` opts into sending selected-project summary metrics; it is off by default. Chat does not execute REPL commands. See [the chat guide](https://github.com/Devesh36/AgentScope/blob/main/docs/chat.md).

The CLI also connects to existing AgentScope servers and provides synthetic incident demos with separate policy, approval, execution, and verification controls.

The REPL includes amber accents, project-aware prompts, grouped `help`, and a
practical `guide` with workflow notes. Explore with `status`, `agents`, `runs`, and
`incidents`; add `--json` for the complete API response. Slash aliases such as
`/help` work too. `run -- COMMAND` launches an app in the watched repository and
waits for exit; use a second terminal for long-running apps. `clear` clears the
visible terminal. Piped sessions and `NO_COLOR` use plain output.

See [the watch guide](https://github.com/Devesh36/AgentScope/blob/main/docs/watch.md) and [CLI reference](https://github.com/Devesh36/AgentScope/blob/main/docs/cli.md).
