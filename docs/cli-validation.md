# CLI and landing page validation

Local checks on 2026-10-09 validated source commit
`ed613783861967ca3b5003d170cf0bb3172acf8a` on
`feat/local-container-acceptance`. See [sanitized measurements](validation/cli-landing-local.json).

- 22 API/SDK/integration tests, 11 CLI tests and 3 web unit tests passed.
  Ruff, mypy, TypeScript and the Next.js production build passed.
- `uv tool install .` installed all three command aliases. `Agenscope Repl`
  provided offline help and connected again after the stack restarted.
- The changed web container built. The unchanged API application reused its
  already validated image. A separate PostgreSQL volume started empty, migrated,
  and passed readiness checks. Both application containers ran as UID 10001 with
  existing resource bounds and loopback-only ports 18010/13010.
- Real SDK ingestion recorded one live run, three spans and four events. A lost
  acknowledgment was retried without duplicate ingestion; replay accepted zero
  events. No events were dropped.
- CLI simulation recorded 25 labeled synthetic runs plus one recovery follow-up.
  The investigation collected eight evidence references. Approval and execution
  were separate; verification remained pending until the observation window and
  reported recovered after **15.88 seconds**. Repeating actions created no extra
  audit records or recovery runs. The follow-up timestamp was after intervention.
- Four Playwright checks passed against containers: desktop/mobile landing with
  working install tabs and clipboard, existing simulation/investigation/approval/
  recovery, API key lifecycle, and restart/reconnection. Anonymous `/` returned
  200; anonymous `/dashboard`, `/settings` and `/api/v1/projects` returned 401.
  Landing rendering made no backend requests. Public page screenshots remain in
  ignored `.local/landing-desktop.png` and `.local/landing-mobile.png`.
- Restart retained the same volume and identical checksums across all twelve
  tables, including investigations, policy settings, approvals and audit records.
  The browser reconnected and replay/action deduplication remained intact. The
  dedicated validation stack was stopped cleanly; its database volume is retained.
  Native SQLite and unrelated Docker resources were not changed.

Reproduce the CLI checks with the commands in [the CLI guide](cli.md).
`npm run accept:containers` now includes CLI unit checks, the live REPL workflow,
its delayed verification, and an additional persistence restart. The measured
checks above were run on a separate initialized stack rather than rerunning that
entire command's native dependency installation and unchanged API build.

## Limitations

Homebrew and Ruby are unavailable here, so actual `brew install`, `brew test`,
and Ruby formula parsing were **not run locally**. The formula's source/launcher
layout passed a Python smoke check without site-packages. A macOS CI job installs
and tests the pinned formula; its hosted result has not been observed. uv uses a
Git source install; no PyPI package, Homebrew core submission, release or external
web deployment was published.

Docker uses the space-intensive `vfs` driver in this 32 GiB environment. The new
web build exhausted available storage and the first PostgreSQL startup failed
clearly with `No space left on device`. Only the two cache records created by that
web build (`zfnhq2jon7o6q3lpyxnbenezs`, `w1u49q87ehjvdu4k16z47hiyb`) were reclaimed,
restoring 1.4 GiB. The successful image and every database volume were retained;
startup and all checks then succeeded. No broad Docker prune was used.
