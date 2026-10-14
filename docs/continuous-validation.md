# 0.4.2 validation record

Measured locally on 14 October 2026 with Python 3.12 and Node.js 24.

| Check | Result |
| --- | --- |
| API/SDK regressions | 33 passed, including current/stale/missing/unexpected migration readiness |
| CLI regressions | 51 passed |
| Dashboard unit tests | 5 passed, including malformed shared links and credential exclusion |
| Phase-history checks | 4 passed; both apps use identical records |
| Production app builds and types | Dashboard and independent landing site passed |
| Public-site export | Homepage, docs, Phase, ten terminal PNGs and PDF verified |
| Watch acceptance | 14 checks passed with local mock provider clients |
| Authenticated container acceptance | 20 named checks passed, including 8 browser scenarios |
| Python dependency scan | 63 locked packages checked; no skips or known vulnerabilities reported |
| Production npm dependency scans | Dashboard and landing scans reported zero known vulnerabilities |
| Workflow configuration | GitHub workflow schema validation passed |
| CLI distribution | Wheel and source archive built; clean wheel prepared services, read API status and stopped gracefully |

Browser coverage includes filtered run/incident URL reloads, clipboard sharing,
dropdown/page history, project changes, debounced searches, cancellation on reset,
empty-page recovery, mobile widths from 320 to 1440 pixels, the investigation and
recovery workflow, one-time API-key display/revocation, public screenshots under
dashboard authentication, protected private routes, and persisted state through
a full stack restart.

The container run first identified a readiness defect: migration startup reached
`002`, but the health check still required `001`. Readiness now compares the
database with packaged migration heads. A separate public-asset defect blocked
the new terminal tour under dashboard authentication; its exact image/PDF paths
are now public while private routes remain protected.

Temporary disk exhaustion interrupted the second container run after its native
checks and image builds passed. Redundant runtime copies created during this task
were removed. The same isolated stack then resumed, preserving passed checks and
executing every remaining check. All 20 named checks passed; its database volume
was retained and its services stopped. This is a completed local validation, not
a claim that an uninterrupted hosted CI run has already passed.

The 5,000-run performance fixture measured a 50.71 ms median overview read
(16 SELECTs) and a 70.43 ms median 500-event update batch (5 SELECTs). These are
local measurements, not production latency targets.

Reproduce with the commands in the [development guide](../README.md#development),
`npm run accept:watch -- --browser`, and `npm run accept:containers`. See the
[development cadence](continuous-development.md) for scheduled checks and the
remaining engineering milestones. Security scans reflect available advisories
at the time of execution. No external paid model calls or compliance/accessibility
certification checks were performed.

The repository's GitHub validation workflow was active and `main` was its default
branch. The new schedule still needs its first scheduled execution. The public
Vercel `/docs` URL returned 404 during this validation; production promotion needs
deployment-account access and remains separate from publishing source to `main`.
