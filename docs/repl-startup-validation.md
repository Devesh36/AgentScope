# Monitoring-first REPL validation

Measured on 16 October 2026 with Python 3.12 and Node.js 24 for the proposed
0.4.3 CLI release.

The REPL now opens directly at its command prompt. Local monitoring does not
require assistant setup. Users explicitly run `configure` before chatting;
configured profiles and hidden credential entry remain supported.

| Check | Result |
| --- | --- |
| CLI regressions | 54 passed, including interactive/piped startup without input or network calls, explicit setup, and preservation of configured profiles |
| Dashboard unit tests | 5 passed |
| Phase-history checks | 4 passed; both apps retain identical history and renderers |
| Dashboard and public landing site | Both production builds and typechecks passed |
| Public static export | Homepage, docs, terminal images and PDF verified |
| Local watch acceptance | 14 checks passed using real provider SDKs against local mock endpoints |
| Browser checks | 5 passed: run/incident views, public landing/docs and live monitoring metrics |
| CLI distributions | Wheel and source archive built successfully |
| Installed wheel first run | Prepared fresh bundled services, read local API status, stopped gracefully; no chat profile or provider key required |
| CI formula preparation | Workflow YAML parsed, shell syntax checked, candidate archive URL/checksum transformation executed against a disposable fixture |

The new startup regression failed against the old implementation because it
requested a provider before reaching the command prompt. It passes after the
change. Provider calls during acceptance used local fixtures, not paid services.

Homebrew CI now installs an archive of the checked-out source rather than an
already-published release tag. This lets pull requests test a proposed version
before release. The published formula retains its versioned Git source.
macOS Homebrew installation requires the hosted CI job and was not run locally.
No release tag was published, and this record does not claim a hosted CI result.

This is one completed development cycle. The requested ten-minute recurring
development cadence remains a goal awaiting a task runner; daily scheduled
quality checks are a separate existing workflow.
