# Verification report — version 0.3, October 5, 2026 update

The existing project was edited in place. User decisions remain: individual publishing under their personal legal name; free first release with no ads or paid features; laptop-local development. Enrollment, hosting and publication remain unapproved.

| Check | Latest executed result |
| --- | --- |
| Exact Docker backend suite | **90 passed, 0 skipped**, October 4 — [output](test-results/2026-10-04/backend-docker.txt) |
| PostGIS integration | **28 passed**, PostgreSQL 16.9 / PostGIS 3.5 image `postgis/postgis:16-3.5`, linux/amd64 on Apple Silicon |
| Unit/rule/geometry/HTTP tests | **62 passed**, including irregular geometry, workload budgets, request deadlines, host/secret guards, privacy and retryable errors |
| Actual runtime HTTP startup | **Passed**, fresh migrations, nonroot Uvicorn, readiness, authentication and recoverable deletion — [output](test-results/2026-10-04/runtime-smoke.txt) |
| Native Swift core executable | **47 checks passed**, October 5 — [output](test-results/2026-10-05/swift-core.txt) |
| Script regressions | **7 passed again October 5** (five release checks, two isolated-runner checks) — [output](test-results/2026-10-05/script-checks.txt) |
| Python lint/format | Passed, October 4 |
| API contract, generated Xcode project, plists and 22 Swift syntax parses | Historical September 18 checks passed; later Swift changes were verified by the full October 3 Xcode build and XCTest run |
| Release configuration | Intentionally incomplete: real production URLs, bundle ID and Apple Team ID remain unset |
| Full iOS Debug build and simulator XCTest | **28 passed**, verified October 5 in Xcode 26.3, iOS Simulator SDK 26.2, iPhone 17 / iOS 26.3.1; no recorded build/test issues — [evidence](test-results/2026-10-05/ios-xctest-summary.json) |
| Manual simulator checks | Sign-in, map, friend acceptance, partial contest settlement, history, results, profile and automatic offline/reconnection behavior verified with synthetic data; remaining account/manual-retry UI checks blocked by simulator window input — [details](testing-2026-10-03.md) |
| Physical GPS, lock screen, battery, deletion UI, accessibility | **Not executed**; use [device checklist](device-checklist.md) and [evidence sheet](device-evidence.md) |
| Public HTTPS, production backups, signing, APNs, TestFlight, App Review | **Not executed**; no enrollment or hosting purchased |

The full Docker run found and fixed a PostgreSQL readiness race before passing. The final suite includes migration up/down/up, friend/nonfriend ownership, partial contests, pre-acceptance offline blocking, concurrent uploads, expiry, rollback, account deletion and session revocation. Deliberate overlap-guard rejection tests print expected SQL errors; the suite passes. Runtime smoke checks then exercised the production image entry point and real committed HTTP requests independently.

All database checks used isolated synthetic `territory_test` databases with no app .env, host data mounts or published ports. Per-run containers/networks were cleaned up; real app data was not modified. Downloaded images/build cache remain local. A separate temporary anonymous Docker client configuration avoided the user's malfunctioning credential helper without changing stored credentials.

Native Swift checks compile shared production sources with Apple frameworks using a temporary VFS overlay for a duplicate Command Line Tools module declaration. The separate full Xcode build and all 28 XCTest cases pass, including the October 5 goal/guidance additions. Neither simulator tests nor native core checks certify real CoreMotion/CoreLocation background lifecycle or battery behavior. See the [October 3 status](testing-2026-10-03.md) for details and remaining owner actions; the October 1 installation blocker is historical.

September 18's historical backend output used a disposable Ubuntu VM with PostGIS 3.4.2; the October 1 exact Docker run supersedes that environment limitation. Historical evidence is retained in test-results. The VM was removed after its run. Current backend output contains five upstream deprecation warnings (Starlette/httpx/AnyIO/Alembic), not failures.

Release limitations remain: existing backup dumps are not purged or reconciled automatically; retention and deletion-aware restoration must precede launch. Manual UI/physical-device acceptance, self-service recovery, abuse controls, policy decisions, hosted availability and operational/load checks remain required. Follow the [production roadmap](production-roadmap.md).

October 4 adds irregular-route regressions and targeted backend hardening. See the [security-readiness report](security-readiness-2026-10-04.md) for exact coverage and uncompleted production gates. No public-production readiness certification is implied.

October 5 adds the three approved daily-running features. See [feature evidence and remaining UI/device checks](daily-features-2026-10-05.md). Backend evidence remains dated October 4 because backend source is unchanged.
