# Local watch validation

Measured locally on **10 October 2026** for the **0.3.0** release.
The [sanitized measurement record](validation/watch-local.json) lists the checks.

The real Python OpenAI 2.54.0 and Anthropic 0.125.0 clients, plus Node OpenAI
7.32.0 and Anthropic 0.133.0 clients, called a loopback mock provider. The test
captured 21 automatic LLM calls and one explicitly instrumented grounding call,
including two expected provider errors. Sync, async, JSON, and SSE responses
preserved their application results and reported usage. No paid provider was used.

The 14 acceptance checks covered automatic service startup, project provisioning,
duplicate watcher rejection, metadata privacy, agent/tool grouping, tool-loop
detection and investigation, explicit grounding, production browser behavior,
shutdown, restart persistence, unexpected parent termination, interactive REPL
monitoring, and application exit codes. Separate API checks verified that
unfinished observations become interrupted when watch stops and later terminal
telemetry can still report the actual outcome.

Both production builds, typechecks, backend lint/types, the API/SDK and CLI suites,
frontend unit tests, and three production browser tests passed locally. The live
dashboard was checked at 320, 390, 768, and 1440 pixels. Wheel and source-archive
builds were inspected for bundled services and exclusion of local state. A clean
wheel install prepared its own API and dashboard and started/stopped successfully.

The grounding fixture supplied two unsupported claims; that count is an external
assessment, not an automatic hallucination diagnosis. External provider behavior,
unlisted integrations, Windows service startup, and the macOS Homebrew job require
their own validation. Homebrew installation and local watch/browser acceptance
are configured in GitHub Actions; hosted results are separate from these checks.
