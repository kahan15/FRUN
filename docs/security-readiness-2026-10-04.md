# Freeform captures and backend hardening — October 4, 2026

This is a tested development build, not a certification that the service is ready for public production. No system can promise that it will never fail. Public release remains blocked on the uncompleted items below. No hosting, enrollment, public upload or paid service was purchased or enabled.

## Captured shape

The rectangles previously visible in Simulator came from synthetic square runs. There is no rectangle grid or bounding-box conversion in the capture implementation. The server projects the accepted GPS segments into metres, removes small GPS noise, finds the enclosed faces, then returns the actual polygon boundaries in GeoJSON. MapKit renders those boundaries, including inward bends and holes. A rectangular route still produces rectangular territory; an irregular route produces irregular territory.

The new [example](examples/freeform-capture.svg) comes from the real capture function. Its [GeoJSON](examples/freeform-capture.geojson) contains both the synthetic recorded route and the captured polygon. The default four-metre simplification produces a maximum boundary deviation of approximately 3.897 m for this example. GPS measurement error itself is additional: the app cannot promise an exact physical boundary. The existing 30 m closure allowance and 200 m² noise floor remain unchanged. Pauses and GPS gaps never join into an invented closing edge.

New regressions verify irregular boundaries and concave cutouts, and send an irregular run through HTTP upload, real PostGIS storage and GeoJSON retrieval. They would fail if a rectangle or convex hull replaced the route. Existing friend-only ownership, independent stranger overlap and contested partial capture tests continue to pass.

## Changes made and verified

| Protection | Behavior now covered |
| --- | --- |
| Upload memory and duration | Oversized declared bodies are rejected before reading; chunked bodies are checked before buffering; one total 60-second body deadline prevents indefinitely slow uploads; disconnected partial requests never reach handlers. |
| Geometry workload | Reject more than 10,000 simplified vertices or 20,000 edge intersections before expensive noding/polygonization. The intersection check processes one edge at a time instead of allocating an all-pairs matrix. Rejected runs are saved with `route_too_complex` and award no land. |
| Login username spraying | A shared per-IP budget applies before password hashing, in addition to the existing per-IP-and-username budget. Attempts use independent database transactions so failed authentication does not erase the counter. |
| Database limits | Runtime connections have 5-second connect/pool waits, 15-second statement limits, 5-second lock waits and 30-second idle-transaction limits. A real PostgreSQL cancellation/rollback/pool-reuse test passes. Migrations use their separate Alembic connection and are not constrained by the runtime statement limit. |
| Retryable outages | Database availability/pool failures return a sanitized 503 with Retry-After. The iOS queue already preserves transient failures for retry. |
| Private HTTP responses | Responses, including errors, carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and a generated request ID. The app's protected offline file cache remains separate. |
| Private diagnostics | Unexpected request exceptions are handled before raw details can reach Uvicorn's traceback logger. SQLAlchemy hides bound parameters, and settings representations/validation messages omit credential values. Tests assert sentinel private values are absent. |
| Explicit production settings | Unknown environment names fail validation. Production rejects wildcard hosts and weak/placeholder signing secrets, applies the host allowlist, and disables interactive API/schema pages. This is a configuration safeguard, not a deployment approval. |
| Runtime pressure | The runtime uses an unprivileged user, bounded log rotation, at most 32 concurrent Uvicorn connections/tasks, a short keep-alive and a bounded graceful shutdown. Real runtime startup/auth/deletion smoke passes with these flags. |

The database options and parameter hiding use documented [SQLAlchemy engine configuration](https://docs.sqlalchemy.org/en/20/core/engines.html). Server concurrency/shutdown controls use documented [Uvicorn settings](https://www.uvicorn.org/settings/). These controls bound specific work; they do not replace capacity testing or edge protection.

## Verification

- **90 backend tests passed, no skips:** 62 unit/HTTP checks and 28 integration checks on the exact PostgreSQL/PostGIS Docker stack. [Log](test-results/2026-10-04/backend-docker.txt).
- **Real HTTP runtime smoke passed:** nonroot Uvicorn, fresh migrations, readiness, registration/login, password guard, account deletion receipt and revoked sessions. [Log](test-results/2026-10-04/runtime-smoke.txt).
- Python lint/format and all seven release/test-runner regressions passed.
- The iOS sources were unchanged in this pass. The latest full iOS build/XCTest result remains **18 passed on October 3**; the native core result remains **31 checks passed on October 1**.
- The tests used synthetic databases in separate Compose projects. Their containers/networks were removed automatically and cleanup was verified. Existing application data was not changed.
- Five existing upstream deprecation warnings remain in the Docker test toolchain; none was a failing assertion.

## Release blockers: do not mark these complete from the test count

| Required before public release | Concrete exit condition |
| --- | --- |
| Physical iPhone acceptance | Record passing locked-screen GPS, background use, permission changes, battery, long-run storage, offline Finish/relaunch/reconnect and accessibility evidence on real hardware. |
| Account recovery and verification | Implement and test expiring, single-use, throttled recovery/verification flows, select delivery only with owner approval, and rehearse recovery without relying on a laptop administrator. |
| Abuse controls | Approve blocking/reporting behavior, implement access checks and an operator moderation workflow, and test unwanted invitations and identity abuse. |
| Retention and deletion-aware restore | Approve raw-route/backup retention; implement purge/reconciliation, test backups restored into a disposable environment, and prove deleted accounts do not reappear after restoration. |
| Production identity/network configuration | Configure approved hostnames, fresh managed secrets, HTTPS, trusted proxy addresses and correct client-IP handling. Keep the direct API/database private. The current `--no-proxy-headers` prevents spoofed forwarding headers; a chosen reverse proxy needs deliberate, tested configuration. |
| Database privileges | Create separate migration and least-privilege runtime roles. The laptop Compose database user is a development convenience, not an acceptable public-production privilege model. |
| Load, failure and operational drills | Measure a stated runner/concurrency target on the actual production-sized service; test lock contention, database/network interruption, full disk, deploy rollback and backup restoration; configure actionable monitoring without raw-route logging. Current geometry/body limits are not a load-test certificate. |
| Dependency and supply-chain review | Review current advisories, base-image vulnerabilities, reproducible build inputs and secret handling before selecting a release candidate. No independent penetration test or complete CVE audit is claimed here. |
| Anti-cheat limits | GPS/pace/continuity checks reduce bad claims but cannot prove physical running or eliminate spoofed client data. Define acceptable abuse handling and review platform attestation separately if needed. |
| Public policy and distribution | Owner approves countries, intended minimum age, support contact, retention, public name, privacy statements, hosting budget and Apple enrollment. Then test a signed release over cellular with the laptop off, followed by TestFlight and App Review. |

Development remains laptop-local. The production switches do not create hosting, configure TLS, buy a domain or enroll with Apple. Follow the [production roadmap](production-roadmap.md) and [physical evidence sheet](device-evidence.md).

## Daily-running improvements — October 5 status update

The owner subsequently approved **1, 4 and 6**, now implemented and tested. See [the feature report](daily-features-2026-10-05.md). Items 2, 3 and 5 remain proposals. The list below records the original designs.

These designs require no added paid API or subscription and can use local storage and native Apple capabilities. They do not remove eventual distribution/hosting costs. They were proposals during the October 4 hardening pass; the implementation status above supersedes that historical state.

1. **Weekly goals and a progress ring:** choose distance or active days, with flexible rest days and no streak penalty.
2. **Optional run reminders:** choose days and time; schedule on the phone, without a notification server. Apple supports [local notification scheduling](https://developer.apple.com/documentation/usernotifications/scheduling-a-notification-locally-from-your-app).
3. **Spoken kilometre/mile updates:** optional distance/time/pace cues using installed system voices, plus haptic feedback, without a paid speech API. See [AVSpeechSynthesizer](https://developer.apple.com/documentation/avfaudio/avspeechsynthesizer).
4. **Clearer run guidance:** GPS readiness, distance back to the start, and an estimated loop preview clearly distinguished from the server's final capture decision.
5. **Private progress charts:** weekly distance, per-run splits and personal bests computed from existing run data.
6. **A simpler running screen:** larger Pause/Finish controls, an accidental-finish safeguard, stronger accessibility labels and text sizing.

Items 2, 3 and 5 require separate owner approval before implementation.
