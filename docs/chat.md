# Chat with AgentScope

AgentScope 0.4.0 adds a conversational assistant to the REPL. Configure its model before chatting, then type questions such as **Who are you?**, **What does AgentScope do?**, or **How do I monitor this repository?** Answers come from the selected model, using AgentScope's product and workflow instructions.

The assistant model is separate from the models your application uses. Selecting Claude for AgentScope does not change an application that uses OpenAI. Chat does not launch processes, edit files, approve proposals, or execute remediation: enter the corresponding REPL commands yourself.

## First session

```bash
agentscope configure
cd /path/to/your/project
agentscope repl
```

Setup asks for the provider, model identifier, profile name, API base when applicable, and a hidden API key if the provider environment variable is absent. Your first interactive REPL also opens this setup when no active profile exists. `0` selects monitoring-only mode; chatting requires model configuration. Piped sessions do not request interactive setup.

Inside the REPL:

```text
model check
Who are you?
What can you help me with?
How do I start monitoring my project?
watch
```

`model check` makes a short real model request, so provider billing and limits can apply. Saving a configuration alone does not verify model access or credentials.

For an existing credential environment variable, configure without entering its value:

```bash
agentscope configure openai --key-env OPENAI_API_KEY
agentscope configure claude --key-env ANTHROPIC_API_KEY
agentscope configure gemini --key-env GEMINI_API_KEY
```

An existing private credential file also works:

```bash
agentscope configure openai --key-file /private/path/openai-key
```

There is no `--api-key` argument. Enter keys through the hidden setup prompt or reference your existing secret configuration. Do not paste credentials into chat.

## Providers

| Setup name | Integration | Default model / authentication |
| --- | --- | --- |
| `openai` | OpenAI Responses API | `gpt-4.1-mini`; `OPENAI_API_KEY` |
| `openai-codex` | Codex model through OpenAI Responses API | `gpt-5-codex`; `OPENAI_API_KEY` |
| `anthropic` or `claude` | Anthropic Messages API | `claude-sonnet-4-5`; `ANTHROPIC_API_KEY` |
| `gemini` or `google` | Gemini generateContent API | `gemini-2.5-flash`; `GEMINI_API_KEY` |
| `openrouter` | OpenAI-compatible chat API | `openai/gpt-4.1-mini`; `OPENROUTER_API_KEY` |
| `groq` | OpenAI-compatible chat API | `llama-3.3-70b-versatile`; `GROQ_API_KEY` |
| `deepseek` | OpenAI-compatible chat API | `deepseek-chat`; `DEEPSEEK_API_KEY` |
| `ollama` | Local OpenAI-compatible API | `qwen3:8b`; no key required |
| `compatible` | Custom OpenAI-compatible endpoint, including local servers | Explicit model and API base; optional `AGENTSCOPE_CHAT_API_KEY` |
| `codex` or `codex-cli` | Installed Codex CLI | Existing CLI login and default model, or `--model` |
| `claude-cli` | Installed Claude CLI | Existing CLI login and default model, or `--model` |

Defaults are starting choices; availability depends on your account and provider. Use `--model` to select another supported identifier. API bases include `/v1` for OpenAI/Anthropic-compatible protocols or `/v1beta` for Gemini. Azure-specific authentication and noncompatible provider protocols need separate adapters.

For Codex or Claude CLI, install and authenticate that CLI first, then configure:

```bash
agentscope configure codex
agentscope configure claude-cli
```

An existing CLI subscription/login and a provider API key are separate authentication methods. `openai-codex` uses an OpenAI API key; `codex` delegates to the installed CLI. AgentScope does not perform their login or install those tools automatically.

CLI chat uses temporary working directories. Codex runs with ephemeral sessions, read-only sandboxing, shell/unified-exec/app/browser/computer features disabled, web search disabled, and an empty MCP server override. Claude runs in print mode with persistence disabled, no built-in tools, and strict empty MCP configuration. Recent CLI versions supporting these flags are required; unsupported flags fail rather than falling back to broader execution.

## Local models

Start Ollama and install the model you choose before configuring it:

```bash
agentscope configure ollama --model qwen3:8b
```

For another compatible local server:

```bash
agentscope configure compatible --name local \
  --model YOUR_INSTALLED_MODEL --base-url http://127.0.0.1:1234/v1
```

Use your server's actual port and model. Remote APIs require HTTPS; loopback HTTP is allowed for local servers. Authentication redirects are rejected.

## Conversation and profiles

```text
chat Explain AgentScope's main capabilities
ask How does watch differ from run?
model providers
model list
model use local
chat reset
```

Ordinary sentences route to chat. Known REPL commands retain their existing behavior; slash-prefixed unknown commands report an error, and likely single-word command typos offer suggestions. Use `chat ...` to ask something that begins with a command name, such as `chat Help me understand monitoring`.

Conversation history stays in memory. The request includes at most ten previous turns, with a bounded character budget; older turns drop from context. Changing provider configuration, selecting another project, toggling project context, or resetting chat clears the previous conversation. Failed or interrupted requests do not append incomplete turns. Exiting the REPL discards its chat history while preserving telemetry.

Named profiles let you switch models without re-entering credentials:

```bash
agentscope configure openai --name fast --model gpt-4.1-mini --key-env OPENAI_API_KEY
agentscope configure anthropic --name review --key-env ANTHROPIC_API_KEY
```

Then enter `model use fast` or `model use review` in the REPL. Configure again with the same name to update a profile.

## Discuss project activity

Project context is **off by default**. After `watch` selects a project, or `use PROJECT_ID` selects an existing project:

```text
context on
Summarize the LLM failures in this project
What do the token and latency metrics tell me?
context off
```

When enabled, each question sends the selected project's current 24-hour summary: run counts, LLM/tool calls and failures, usage, estimated cost, incident count, grounding assessment totals, latency percentiles, and update time. It excludes source files, raw traces, prompts, generated content, credential values, and individual incident details. The assistant does not have repository access or a full incident investigation merely because summary context is enabled.

Use `runs`, `incidents`, and `investigate INCIDENT_ID` to inspect the authoritative records. Chat interpretations are generated suggestions, not new detector findings. Unsupported claims remain **Not evaluated** until the application supplies grounding assessments; a successful LLM request does not establish factual accuracy.

## Storage and errors

Profiles live in `~/.agentscope/chat/config.json`, or under `AGENTSCOPE_HOME/chat`. The file stores credential references, not key values. Hidden-entry keys are saved separately with mode `0600`; managed chat directories use mode `0700`. External credential files are referenced without being copied or modified.

Your questions, conversation context, and optional project summary go to the selected model provider. AgentScope does not save the conversation or add its text to application telemetry. OpenAI requests use `store: false`; other provider retention follows that provider's policy.

`model status` shows configuration and local credential/CLI availability without making a model call. `model check` verifies the actual connection. Missing keys, unavailable CLIs, rejected models, rate limits, malformed responses, and timeouts produce explicit errors. API error bodies and credentials are excluded from error output; failed calls never receive a canned substitute answer.

The provider protocol tests use local HTTP fixtures, and CLI adapter tests use isolated executable fixtures. A separate conversational demo uses genuine local SmolLM2 inference. Paid-provider accounts and live Codex/Claude CLI authentication require the user's configured credentials and have not been validated in this environment.

See the [sanitized local validation record](validation/chat-local.json) for the measured release checks.
