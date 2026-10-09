# AgentScope CLI

An interactive client for an **existing AgentScope API**. It does not start Docker,
bundle a database, or substitute canned results for unavailable services.

Install from the repository with `uv tool install .`, then run `agentscope repl`.
`Agenscope Repl` is a supported alias. Python 3.12+ is required.
Type `help` to see commands; help and `--version` work offline.

See [the installation and demo guide](../../docs/cli.md) for uv, Homebrew,
authentication and the explicit simulation → investigation → approval → execution
→ recovery workflow. This administration client is separate from `agentscope-sdk`.
