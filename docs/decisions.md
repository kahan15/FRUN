# Implementation decisions and limits

## Local architecture

The server and database run entirely on the laptop. The native client talks to `/api/v1` over the configured local address. Only the API port is published; Postgres is not exposed on the LAN. Compose persists PostgreSQL under the project directory, so moving to another disk is a normal backup/restore operation. No application data is uploaded to a managed hosting service.

SwiftUI handles presentation, CoreLocation records fixes, and CoreMotion supplies optional steps. The phone may calculate display distance and elapsed time, as required by the specification, but never computes territory or an authoritative cheat verdict. The server recomputes both distance and area. Server area uses `ST_Area(geom::geography)`.

The backend uses SQLAlchemy 2 sessions and parameterized SQL in repositories. It deliberately uses explicit SQL rather than a duplicate ORM mapping of the spatial schema. Alembic owns the schema. Routers do HTTP, services implement rules, repositories own SQL, and geometry remains pure. Each game request has one transaction. Auth throttling uses a separate small transaction so failed sign-in attempts survive the authentication rollback.

## Corrections to the supplied specification

1. **A centroid grid-cell lock is insufficient.** Two intersecting polygons can have centroids in different cells. This version uses one transaction-scoped advisory lock for claims, expiry, and friendship changes, plus row locks and a deferred database overlap guard. The app is deliberately small; this serialization is an acceptable correctness tradeoff. A scale-out change must lock every spatial cell touched by a claim and every possible affected footprint, in sorted order. Never remove overlap tests. Direct SQL writers must take the same advisory lock before changing active geometry; only the application/maintenance repository is an authorized game writer.
2. **Pauses cannot draw imaginary paths.** A GPS journal has segment IDs. A pause or loss of GPS creates a segment boundary. The database therefore stores a `MULTILINESTRING` instead of a `LINESTRING`. Each segment must enclose its own face; the result is unioned before claiming. A route sealed only by joining across a pause claims nothing. This prevents driving while paused from drawing a territory edge.
3. **Upload order decides the latest claim.** Phone timestamps are untrusted and offline uploads may arrive hours later. Server transaction order defines `claimed_at`, expiry, and cooldown. This is deterministic and prevents a modified client from backdating a steal. The original start/end timestamps are retained for the run history/audit, but are not an ownership priority.
4. **The current request replaces global exclusivity.** Non-friends own overlapping areas independently. Only direct accepted friends affect a claim; friend-of-friend access is not inherited. Acceptance records the existing pairwise overlap without moving land. A qualifying run started after acceptance can immediately settle its captured portion, in server transaction order. Older offline runs are blocked on that contest even if ordinary cooldown has expired. A runner who is friends with both owners can also capture their visible contested ground. Multi-owner stolen area is geographically unioned; per-victim notifications report each victim's loss. There are no competition objects.
5. **World-record interpolation is a heuristic, not proof of cheating.** A record is an observed performance, not a physical law. A power law between a few events can miss faster performances at intermediate distances. The configured 5% margin reduces this risk; rejection copy says a check failed, not that a runner cheated. Suspicious strides remain flagged and awarded. Client-supplied steps and timestamps are not attestation.
6. **Do not auto-reject ultras using an unverified extrapolation.** The function extrapolates, but outside 100 m through marathon distance (with 1% endpoint tolerance) pace alone only flags. Sprint/burst and timestamp checks still apply. A complete WA/DUV ultra table has not been independently verified. This is a deliberate temporary relaxation to avoid false accusations.
7. **Push is opt-in.** The in-app feed is available in the zero-purchase personal build. APNs code is present but the worker/profile and entitlements are off. It contacts Apple's infrastructure when explicitly enabled, so it is also outside a strictly local-only deployment.

## Pace anchors

The bundled tables are conservative performance anchors, not a promise of a live, ratified record registry. Distances are metres and times are seconds. Both tables can be replaced via JSON environment values `PACE_RECORDS_MEN` and `PACE_RECORDS_WOMEN`; they must be strictly increasing.

| Distance | Men's time | Women's time |
| --- | ---: | ---: |
| 100 m | 9.58 | 10.49 |
| 400 m | 43.03 | 47.60 |
| 1,500 m | 206.00 | 228.00 |
| 5,000 m | 755.36 | 838.06 |
| 10,000 m | 1,571.00 | 1,734.14 |
| Half marathon | 3,402.00 | 3,772.00 |
| Marathon | 7,170.00 | 7,796.00 |

Checked against World Athletics material while building: [Cheptegei's profile](https://worldathletics.org/athletes/uganda/joshua-cheptegei-14645612) supports the men's 5,000/10,000 anchors; [Sawe's London performance](https://worldathletics.org/competitions/world-athletics-label-road-races/news/sawe-two-hour-assefa-world-record-london-marathon) supports 1:59:30. The men's half anchor deliberately preserves the faster 56:42 performance ceiling even though it is not a currently ratified record; the purpose is permissive validation. The 1,500 m women's anchor is rounded down, also permissively. The short-distance and remaining historical anchors need a full official-source refresh before wider release. This limitation is explicit; no fabricated DUV verification is claimed.

## Known first-version limits

- Real PostGIS tests and native shared Swift checks have been executed; full iOS build, XCTest, UI, and physical background tracking remain device/Xcode gates. See the current verification report.
- API serves at most the most recent 2,000 territory rows per map request. This is a bounded laptop-phase map, not a city-scale viewport query system. Leaderboard/stats remain complete. Add viewport pagination before a friend group reaches this cap.
- Partial carving updates the current polygon; raw uploaded runs and steal payloads remain available, but there is no historical polygon-version timeline. Fully lost and expired rows remain on the past-territory endpoint.
- Renewal splits the captured slice from the untouched remainder. Ordinary renewal preserves protection time; settling an already-owned contested slice gives that slice fresh protection. Spatial calculations and the deferred guard ignore at most 0.0001 m² (one square centimetre) of floating-point boundary dust, preventing false steals and transaction failures along shared edges.
- Raw GPS and audit payloads are retained indefinitely on the laptop. No hidden pruning is performed. The storage script reports actual use; retention policy should be chosen with the user before deleting history.
- The server splits at raw inaccurate samples, segment changes, and gaps longer than 30 seconds, even if a client omits a segment boundary. Such gaps add no distance, duration, or closing edge. Timestamp ordering is checked even on discarded fixes. Burst/teleport checks apply only to continuous accurate observations.
- UTM supports latitude −80° to +84°. Antimeridian-crossing routes and combined run extents over 100 km are rejected with a supported-extent reason, rather than calculating misleading geometry.
- iOS limits one recorded run to 60,000 accepted fixes. The client pauses with a visible message at the limit. Motion denial does not block tracking.
- APNs is at-least-once: a process crash after Apple accepts a push but before the database commit can cause a repeat. Collapse IDs reduce duplicates but are not an exactly-once guarantee.
- Expiry survives server restarts; map/stat queries independently filter expiry, so a delayed worker cannot revive expired ground. Changing expiry mode affects new claims/renewals, not existing rows retroactively.
- A failed refresh response can require sign-in again because refresh tokens rotate. Run files survive; there is no paid email/password recovery service. Password reset is a laptop-admin operation.
- No public-release approval, App Store submission, external user invites, paid Apple membership, or internet exposure has been performed.

## Background recording and offline recovery

Tracking remains on native `CLLocationManager` with fitness activity, automatic pausing disabled, the location background mode, and the visible background indicator. It starts in the foreground with When In Use permission; the app no longer requests Always merely for a foreground-started run. Precise Location is required, with a temporary accuracy purpose string. Apple's documented behavior: [background authorization](https://developer.apple.com/documentation/CoreLocation/requesting-authorization-to-use-location-services) and [background updates](https://developer.apple.com/documentation/corelocation/cllocationmanager/allowsbackgroundlocationupdates).

Delayed callback batches are checked against the recording interval instead of a 15-second age cutoff. Fixes before resume, duplicate timestamps, future timestamps, inaccurate fixes, and interrupted segments cannot invent edges. Every accepted journal append is synchronized; metadata and queues use atomic writes and protection available after first unlock. Motion callbacks have a session generation so late callbacks cannot corrupt resumed step counts.

A crashed process recovers paused and keeps the original run UUID. Complete journal lines survive; only a torn final append is repaired. Complete-line corruption is reported and preserved. Queue/receipt markers take precedence over leftover active metadata after Finish, preventing a completed run from being resumed. Corrupt markers cannot authorize deletion of active data.

Sync retries automatically while the app can execute, with bounded exponential backoff, foreground/network reconnect triggers, and a manual override. A short UIKit background task gives an in-flight upload time to complete after lock; iOS may still suspend it. Recording is offline; syncing needs the laptop. Pending payloads survive interruption, and the backend UUID makes a lost response safe to retry. Receipts must match the uploaded UUID before removing data. Declined uploads move into a preserved needs-attention folder and can be retried manually; one corrupt or declined file does not starve the rest.

Force-quitting or rebooting does not promise continuous GPS recording. Cached maps may be stale offline, including friendship changes made elsewhere; server authorization always uses the current accepted friendships. A confirmed local removal clears cached friend overlays immediately.

The supplied original specification is retained as historical reference. Its global ownership/hidden blocking text is superseded by the user's current request and these implemented rules.

## Production preparation, September 18, 2026

The owner confirmed individual publishing under their personal legal name, and a free initial app without advertisements or paid features. No enrollment or hosting purchase is authorized yet. The current work adds account deletion and privacy/release preparation; the production roadmap distinguishes remaining engineering from owner device/identity/policy/spending actions. A stable public HTTPS service is needed for public distribution; development remains on the laptop.
