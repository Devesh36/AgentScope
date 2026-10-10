# Development phases

The public homepage includes **Phase** in its navigation, linking to `#phase`.
The timeline explains the product's evolution, newest phase first, with a UTC
date and GitHub source link for each recorded commit. Both public homepages
render the same history.

## Record a change

Update `apps/landing/lib/development-phases.json` and its identical copy in
`apps/web/lib/` as part of every implementation task. Add the change to an
existing phase, or append a new phase for a distinct milestone. Each change has:

- `subject`: the exact Git commit subject.
- `sha`: the full commit hash, or `null` for the commit being prepared.
- `date`: the UTC calendar date, in `YYYY-MM-DD` format.
- `phase`: the matching phase ID.
- `title` and `summary`: a concise description of what changed and its effect.

The build resolves a prepared entry's subject to its actual commit hash and date.
Before that commit exists, the entry displays **This update**. On the next task,
fill in its hash so builds without Git retain the source link. Multiple commits
in a task each need their own entry. Record implemented outcomes of chats rather
than conversation transcripts or uncompleted plans.

## Build behavior

The server component reads the checkout's Git log while Next.js prerenders the
homepage. New commits without curated descriptions appear in **Continued
development**, using their public commit subjects and exact dates. Rebuild or
redeploy to publish changes; the page does not poll GitHub from the browser.

The checked-in snapshot retains earlier commits when a checkout is shallow or
Git is unavailable, including Docker and source-archive builds. Such builds can
only show the snapshot and any commits present in the checkout. For complete
automatic discovery of uncurated commits in CI, fetch the full Git history.

Do not include private chat text, credentials, or local telemetry. The history
starts with the earliest commit available in this repository; it does not claim
to describe work before that baseline.

## Verify

```bash
node --test scripts/test-phase-history.mjs
npm --prefix apps/landing run build
npm --prefix apps/landing run typecheck
npm --prefix apps/landing run verify
npm --prefix apps/web run typecheck
# With the local web server running:
npm --prefix apps/web run test:e2e -- --project=workflow tests/e2e/landing.spec.ts
```
