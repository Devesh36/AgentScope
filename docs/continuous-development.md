# Continuous development

AgentScope is being developed as a dependable self-hosted observability tool.
The current release supports local development and evaluation. It is not yet an
enterprise multi-user service or a certified compliance product.

See the [0.4.2 validation record](continuous-validation.md) for measured checks,
the container regressions fixed in this pass, and remaining publication limits.

## Automatic quality checks

The [Validate workflow](../.github/workflows/ci.yml) runs on every push and pull
request, manually through GitHub Actions, and daily at **03:30 UTC / 09:00 India
time** on the default branch. Monday's scheduled run also exercises containers
and Homebrew installation. GitHub can delay scheduled workflows; this is a
maintenance cadence, not a guaranteed execution time. Actions must be enabled
and `main` must remain the default branch.

Daily runs check Python lint/types/tests, CLI tests and installation, dashboard
types/tests/build, the independent public-site export, provider capture and
browser behavior, a reproducible performance fixture, and dependency advisories.
Python advisories fail the audit; production npm advisories fail at high or
critical severity. Registry/advisory failures also fail the job instead of
reporting a clean scan. Performance measurements and sanitized acceptance
reports are available in Actions artifacts. Reports never include tokens,
credentials, raw application traces, or model content.

The schedule runs checks. It does **not** start an AI developer, upgrade
dependencies, open branches, or publish to production. To schedule development
tasks themselves, connect a recurring Codex task runner to this repository with
the instructions below. This cloud session has no recurring task-runner tool.

To change the cadence, edit the two cron expressions in `ci.yml` together and
their corresponding Monday-only job conditions. Keep expensive acceptance jobs
weekly; run lighter checks daily. Increase frequency after a release regression,
and reduce it when CI duration or maintenance costs warrant it.

## Development loop

1. Inspect `main`, current instructions, the latest Actions failures, and this
   backlog. Preserve existing work and use `main` directly.
2. Address a failing safety or correctness check before adding a feature.
   Otherwise choose one complete user workflow from the next milestone.
3. Implement the smallest useful release, with accessible keyboard controls,
   responsive layouts, truthful metrics, actionable empty/error states, and
   metadata-only telemetry by default.
4. Run checks appropriate to the changed behavior, plus both app typechecks and
   public export/history checks. Exercise API-to-browser behavior when changing
   the dashboard. Package bundled runtime changes under a new CLI version.
5. Record measured outcomes and outstanding limits. Update the public Phase
   timeline with the exact commit subject and UTC date. Push passing changes to
   `main`; create no feature branches or automated dependency-update branches.
6. Review the result weekly, reorder the backlog from user feedback and observed
   failures, and choose the next bounded task. Keep production promotion separate
   until the deployment account is available and the deployment is verified.

## Engineering baseline

| Area | Current evidence | Next required work |
| --- | --- | --- |
| Data integrity | Idempotent ingestion, project-scoped keys, persisted investigation/recovery evidence, API regression tests | Larger-volume PostgreSQL and retention/backup acceptance |
| Local reliability | Watch lifecycle, ownership locks, shutdown/restart and live-stream reconnect acceptance | Longer soak tests and interrupted-install recovery |
| Privacy and access | Credential-file protection, hashed/revocable ingestion keys, metadata-only capture, opt-in assistant summaries | Multi-user identity, authorization roles, session lifecycle and audit export |
| Usability | Responsive dashboard, URL-based run/incident views, debounce, explicit recovery from empty pages, keyboard controls | Accessibility audit, saved views, trace comparison and export |
| Release quality | Locked dependencies, builds, tests, installation checks, scheduled advisory checks and dated Phase records | Release provenance, migration/rollback rehearsals and production deployment verification |
| Scale | Batched ingestion, indexed history, measured 5,000-run fixture | Bounded agent/trace lists, cursor pagination and coordinated workers |

The 0.4.2 pass also restores public access to the exact ten published terminal
images and tour PDF when dashboard authentication is enabled. The previous asset
allowlist covered only the original two screenshots; all other workspace routes
and unpublished asset paths still require dashboard access.

Container readiness now compares the database revision set with the packaged
Alembic migration heads. The previous check required `001` even after startup
upgraded storage to `002`, leaving a migrated API unhealthy. Missing, stale, or
unexpected revisions still return 503.

Passing these checks is evidence for specific engineering practices. It does not
establish SOC 2, HIPAA, PCI DSS, ISO certification, or full WCAG conformance.

## Prioritized milestones

1. **Usable monitoring workflows:** shareable run/incident views (delivered in
   0.4.2), saved views, trace export with explicit content controls, and keyboard
   and screen-reader review of the investigation workflow.
2. **Operational reliability:** retention acceptance, database backup/restore,
   migration recovery, longer watch soak tests and PostgreSQL load fixtures.
3. **Team access:** user authentication, project roles, scoped permissions,
   session expiry and exportable administrative audit records.
4. **Integration depth:** more provider capture adapters with sync/async/stream
   coverage, explicit SDK boundaries, clearer usage/pricing coverage, and
   evaluation results tied to reference evidence.
5. **Production operations:** coordinated workers, ingestion limits, deployment
   health checks, release provenance and rollback validation.

Milestones are a prioritized backlog, not promises of delivery dates. Each
development task should revise this ordering when concrete evidence changes it.
