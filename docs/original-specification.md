> Historical reference. The current user request supersedes global ownership, hidden stranger blocking, and separate competition concepts. See decisions.md and README.md for version 0.2 behavior.

# Territory Run — Full Build Specification

> **How to use this prompt.** Paste the whole thing. Then add one line at the
> top saying what you want done with it, e.g.:
>
> - *"Build this from scratch. Start with the backend, and stop after the geometry engine and its tests so I can verify them."*
> - *"Review this design and tell me where it breaks at 10,000 users."*
> - *"I have this built. Implement Phase 4 (APNs delivery worker)."*
>
> Without that line the model will guess. Everything below is the shared
> context it needs regardless of which task you pick.

---

## 1. What we are building

An iOS app that turns running into a territory-capture game.

The user runs. The phone traces their GPS path. When that path encloses an area
— a lap around a block, a loop through a park — the enclosed ground becomes
their **territory**, drawn on the map. Territory decays after 30 days. Friends
can take each other's territory by running over it.

The competitive scope is deliberately small: **you only ever see and compete
with your accepted friends.** No global leaderboard, no strangers on your map.
A stranger taking "your" park 400 km away is meaningless; your roommate taking
it is a group-chat event. That scoping is the product, not a privacy setting.

### Core loop

1. Press Start. Run.
2. Press Finish. The track uploads.
3. The server checks the run is physically plausible, extracts every closed area the path sealed off, and resolves those areas against existing territory.
4. The map updates. If you took ground from a friend, they get notified.
5. Territory you hold expires in 30 days unless you re-run it.

### What makes it a game rather than a map

- **Decay.** Holding territory requires re-running it. There is always something about to lapse, so there is always a reason to run today.
- **Theft.** A friend can take your ground, and you find out via push notification. This is the entire retention mechanic.
- **Scarcity.** Two people cannot own the same ground. Every claim is somebody's loss.

---

## 2. Non-negotiable design rules

These are decided. Do not re-litigate them unless you have a concrete reason,
in which case say so explicitly rather than quietly changing the design.

| Rule Decision            |                                                                                                                |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| What counts as territory | Only **closed loops**. A straight line or an out-and-back claims nothing.                                      |
| Who can take your land   | **Accepted friends only.** Non-friends' territory is invisible and immune.                                     |
| How theft works          | Take only the **overlapping slice**, carved out of the victim's polygon. Not a whole-territory swap.           |
| Conflict resolution      | Last-timestamp-wins **plus** a per-territory steal cooldown (default 6 h).                                     |
| Lifetime                 | 30 days from claim, rolling per territory. A hard monthly-reset mode is also implemented behind a config flag. |
| Re-running your own land | Refreshes its expiry. Adds **no** area.                                                                        |
| Overlap invariant        | **No two active territories ever overlap, for anyone.**                                                        |
| Client trust             | Zero. The phone records and uploads; it computes no area and makes no cheat decision.                          |

**Why the overlap invariant matters:** it is what allows the leaderboard to be
`SUM(area_m2)` instead of an `ST_Union` over thousands of polygons on every
request. It is enforced by subtracting at write time, and guarded by a test.
Never relax it.

**Why partial carving rather than whole-territory capture:** a small loop inside
a friend's big one should punch a hole, not take the block. The trade is that
total conquest becomes hard — if playtesting shows the game lacks drama, add
"fully enclosing a friend's territory takes all of it" as a special case.

---

## 3. The geometry engine (the heart of the system)

This is the part that carries the whole product. Get it right first; nothing
else matters until it works.

### The algorithm

A run is a single polyline that crosses itself. **Node that polyline at every
self-intersection, then polygonize the result.** That one operation yields every
enclosed face for free, with no special-casing:

| Route Result                         |                                        |
| ------------------------------------ | -------------------------------------- |
| Square lap                           | one fragment                           |
| Figure-eight                         | two fragments                          |
| Lollipop (stem out, loop, stem back) | one fragment — the head only           |
| Out-and-back on the same path        | nothing                                |
| Straight line                        | nothing                                |
| Sloppy overlapping laps              | exactly the ground actually sealed off |

In Shapely this is `polygonize(unary_union(line))`. The naive alternative —
"did the run end where it started" — needs special cases for every row above and
still fails on the last one, which is what real runs actually look like.

### Two details that do heavy lifting

**Simplification at \~4 m (Douglas-Peucker), applied to the projected track
before noding.** Without it, standing at a traffic light produces a knot of
micro-intersections that polygonize into hundreds of sliver "territories".

**Auto-close a gap under \~30 m.** Runners stop across the street from where they
started. Without snapping that shut, the final lap bounds no face and the user
gets nothing for a run they experienced as a complete loop. This single line is
the difference between "the app is broken" and "the app works" in user testing.

### Projection

Store everything in EPSG:4326. But simplification tolerances and areas are
meaningless in degrees, so project into the UTM zone under the run's centroid,
do the metric work there, and project back. Over a single run — tens of km at
most — UTM distortion is sub-metre. Cache the transformer pair by EPSG code.

Use PostGIS `ST_Area(geom::geography)` for the authoritative area number shown
to users; UTM area is fine for internally filtering fragments.

### Noise floor

Discard fragments under \~200 m². This is jitter filtering, **not** a gameplay
minimum — say so in comments, because the two get confused.

---

## 4. Anti-cheat

The ceiling is the **world-record pace curve**: nobody has ever averaged faster
than the record over a given distance, so a submission that beats it is fake.
This is defensible and needs no arbitrary "seems too fast" threshold.

Layer the checks cheapest-first:

| # Check Verdict on failure  |                                                            |                                            |
| --------------------------- | ---------------------------------------------------------- | ------------------------------------------ |
| 1                           | GPS fix accuracy worse than 30 m                           | dropped silently, before anything reads it |
| 2                           | Non-monotonic timestamps                                   | rejected                                   |
| 3                           | Teleport: >250 m in <120 s with no fixes between           | rejected                                   |
| 4                           | Burst speed >12.5 m/s over one segment                     | rejected                                   |
| 5                           | **Average speed vs. world record for that exact distance** | rejected                                   |
| 6                           | Pedometer stride implies <0.4 m or >2.6 m per step         | **flagged**, not rejected                  |

### Rejected vs flagged — this distinction matters

- **Rejected** = physically impossible. No territory. Run stored for audit.
- **Flagged** = suspicious but survivable. **Territory IS awarded**, and a human can review later.

Auto-rejecting the merely-odd is how you lose the user whose GPS glitched in a
tunnel. False negatives are recoverable; falsely rejecting someone's completed
run is not.

### Interpolating the record curve

Between record points, use a Riegel-style power law (`t = a · d^b`) fitted to
the bracketing pair, because that is genuinely how endurance performance scales
with distance. Beyond the table, extrapolate off the last two entries — it
flattens realistically for ultras.

Maintain separate men's and women's tables (records differ by roughly 10%, so
one shared curve either lets women cheat or falsely rejects fast men). Users may
decline to state it, in which case apply the more permissive curve. **Store this
field for the pace ceiling and nothing else** — never display it, never share
it, and say so in the signup UI copy.

> ⚠️ **Verify every record against World Athletics (track/road) and DUV (50 km+)
> before shipping.** They are generous ceilings so small errors are harmless,
> but a running app quoting wrong records is an avoidable embarrassment.

### Audit trail

Store the full verdict as JSONB on the run row. When you retune thresholds, you
can replay historical runs against the new rules instead of guessing at your
false-positive rate. Log every rejected and flagged run with its reason from day
one — the false-rejection rate is the number you will most wish you had.

---

## 5. Claim resolution (the game rules in code)

Given the polygons a runner just enclosed, in this exact order:

1. **Subtract land owned by non-friends.** Strangers are invisible and immune.
2. **Subtract friends' land still inside its steal cooldown.**
3. **Steal what still overlaps a friend** — only the overlapping slice. Update the victim's polygon to the difference; if nothing remains, deactivate their row and record who took it. Write a notification in the same transaction.
4. **Subtract your own existing land** so area never double-counts, and instead push its `expires_at` forward. Re-running your turf is how you maintain it.
5. **Whatever survives becomes a new territory row.**

Write this so it reads as five numbered decisions. Keep the SQL in a repository
layer so the rules stay legible.

### Concurrency — do not skip this

Two friends finishing runs in the same park at the same second will both read
"this ground is free" and both insert, silently breaking the overlap invariant.
Row locks alone do not fix it, because the race happens before either write.

Two mechanisms together:

- **`pg_advisory_xact_lock`** **keyed on a coarse \~5 km grid cell** derived from the claim centroid. Claims near each other serialise; claims in different cities never block. Transaction-scoped, so nothing needs cleaning up.
- **`SELECT ... FOR UPDATE`** on the territory rows about to be carved.

### Geometry hygiene

`ST_Difference` occasionally emits self-touching rings that PostGIS then refuses
to insert. Normalise every result through `buffer(0)` and coerce to MultiPolygon
before writing.

---

## 6. Data model

**users** — id, email, username, password\_hash, display\_name, sex (`M`/`F`/`X`,
pace curve only), is\_active, timestamps.

**friendships** — requester\_id, addressee\_id, status (`pending`/`accepted`/
`blocked`). Needs a **unique index on the unordered pair**
(`least(a,b), greatest(a,b)`) so A→B and B→A cannot both exist.

**runs** — user\_id, **client\_run\_id (UUID, unique)**, started\_at, ended\_at,
duration\_s, distance\_m, avg\_speed\_ms, point\_count, dropped\_point\_count,
step\_count, track (LINESTRING 4326), status, review\_notes, **cheat\_report
(JSONB)**, fragment\_count, claimed\_area\_m2, stolen\_area\_m2.

**territories** — owner\_id, run\_id, **geom (MULTIPOLYGON 4326)**, area\_m2,
claimed\_at, expires\_at, active, stolen\_from\_id, lost\_at, lost\_to\_id.

**notifications** — outbox pattern: user\_id, kind, title, body, payload JSONB,
read\_at, delivered\_at. Written inside the transaction that caused the event, so
a rolled-back claim never produces a phantom "you were robbed" push. Same table
backs the in-app feed.

**devices** — user\_id, apns\_token (unique), platform, app\_version, is\_active.

### Indexes that matter

- **Partial GiST on** **`territories.geom WHERE active`** — the single most important index in the schema. Every upload runs `ST_Intersects` against active territory; a partial index keeps expired rows out of the tree entirely, which compounds over months.
- `(owner_id, active)` on territories; `(expires_at, active)` for the expiry job.
- Unique on `runs.client_run_id`; `(user_id, created_at)` for the rate limiter.
- Partial index on `notifications WHERE delivered_at IS NULL` for the push worker.

### Idempotency

The phone generates a `client_run_id` UUID when the run **starts**. Phones lose
signal mid-upload and retry; without this key, one run mints territory twice. On
a duplicate, return the original result with a `was_duplicate` flag rather than
reprocessing. The iOS offline retry queue is only safe *because* of this.

---

## 7. Backend stack and structure

Python 3.12, FastAPI, SQLAlchemy 2.x, PostgreSQL + PostGIS, Shapely, pyproj,
Alembic, structlog. Docker Compose for local.

```
backend/app/
  main.py           application factory
  core/             config, logging, security, errors, deps, middleware
  db/               engine, session, declarative base
  models/           ORM tables
  schemas/          Pydantic request/response contracts
  repositories/     ALL SQL, including every ST_ function
  services/         game rules — the only layer with decisions in it
  geo/              pure geometry: loops, projection, anticheat
  api/v1/routers/   HTTP only, no logic
  workers/          expiry job as a standalone process

```

**The layering rule:** routers do HTTP, services decide, repositories do SQL,
`geo/` does mathematics and knows nothing about anything else. `geo/` having no
I/O is what makes it fast to test — and those are the tests to trust most.

### Specific requirements

- **Migrations, never** **`create_all()`****.** `create_all` cannot express the PostGIS extension, the partial GiST index, or the unordered-pair unique index. It also silently diverges from production on the first column change. CI should verify migrations roll back and forward cleanly.
- **One transaction per request**, committed by the session dependency. Services never call `commit()` themselves, so a multi-step claim (reject a run + carve three territories + insert one + write two notifications) is genuinely atomic.
- **Every game rule is a config setting**, not a constant. Cooldown length, fragment floor, pace margin, simplify tolerance — these are what you will tune weekly once real users are running, and you do not want a deploy per tweak.
- **Structured logging** with a request ID in a contextvar, echoed as `X-Request-ID`. Console-pretty locally, JSON in production.
- **One error vocabulary** — every failure returns `{"error": {"code": ..., "message": ..., "details": ...}}` and the client switches on `code`, never on the message.
- **Expiry as a standalone process**, runnable once or as a loop. An asyncio task inside the API would run N times concurrently under N gunicorn workers and die silently with any worker restart.
- **Rate limiting off the runs table** (one indexed COUNT per upload). Cheaper than operating Redis at this scale; keep it in one method so it is easy to swap later.
- **`/health/live`** must not touch the database (a DB blip should not make the orchestrator kill healthy pods). **`/health/ready`** checks Postgres and PostGIS.
- Multi-stage Dockerfile; production stage runs as a **non-root user**.

### API surface (v1)

```
POST   /auth/register  /auth/login  /auth/refresh
GET    /auth/me

GET    /friends                      friends + incoming + outgoing
GET    /friends/search?q=
POST   /friends/request  /accept  /remove

POST   /runs                         upload; returns the claim outcome
GET    /runs                         history, paginated

GET    /territories?state=current|past    GeoJSON FeatureCollection
GET    /territories/stats
GET    /leaderboard                       friend-scoped

GET    /notifications  /notifications/unread-count
POST   /notifications/read-all
POST   /devices                      APNs registration

GET    /health/live  /health/ready

```

The run-upload response should carry everything the result screen needs:
status, reasons, fragment count, new area, refreshed area, blocked area, and a
list of steals with victim usernames.

---

## 8. iOS client

Swift 5.10, SwiftUI, iOS 17+, MapKit (`Map` with `MapPolygon` / `MapPolyline`),
CoreLocation, CoreMotion. XcodeGen (`project.yml`) so the project file is not in
version control.

### Screens

- **Auth** — register/login. The sex picker needs copy explaining it is only for the cheat-detection pace ceiling and is never shown to anyone.
- **Map** — live trace in green, your territory blue, friends' orange. Start / Pause / Finish. Live distance, elapsed, current GPS accuracy.
- **Result sheet** — three distinct states: rejected (with reasons), no loop closed (with an explanation of *why* and what to do differently), or claimed (area, fragment count, steals, refreshed land, blocked land).
- **Leaderboard** — friend-scoped, add-by-username, accept incoming requests.
- **History** — past runs with status badges.
- **Profile** — stats, notification feed, sign out.

### Client requirements

- **Tokens in the Keychain**, not UserDefaults (which is a plist readable from a backup and not wiped on uninstall).
- **Transparent 401 → refresh → retry once**, with concurrent refreshes collapsed into a single task so several simultaneous failures do not each burn a refresh token.
- **Base URL from Info.plist per build configuration**, so a TestFlight build cannot point at localhost.
- **Filter fixes on device before appending**: drop accuracy >30 m, drop stale timestamps, drop movements under 2 m (standing still). Bad fixes are precisely what create phantom loops.
- **Request** **`Always`** **location only when the user first presses Start**, not at launch. The prompt makes sense at that moment and is far more likely to be granted. Enable `allowsBackgroundLocationUpdates` and `showsBackgroundLocationIndicator`; disable when the run ends.
- **Persist failed uploads to disk and retry on launch.** Losing a completed run is the single most infuriating failure a running app can have.
- **Compute nothing.** No area, no cheat decision. A client that scores itself is a client that can be patched to claim the city.

---

## 9. Testing

**Unit tests (pure, no database, must run in seconds)** — these are the ones to
trust. Cover at minimum:

- square lap → one fragment, correct area
- straight line → nothing
- out-and-back → nothing
- figure-eight → two fragments
- lollipop → one fragment, head only
- near-miss lap (15 m short) → snaps shut
- genuinely open lap (200 m short) → does *not* snap
- GPS jitter along a line → zero area
- loop inside a loop → not double-counted
- ordinary 5k accepted; elite 13:30 5k accepted; 1:50 marathon rejected
- real 3:30 marathon accepted
- women's curve stricter; curve monotonic across all distances
- cycling stride → flagged, not rejected
- teleport → rejected; all-fixes-dropped → rejected

**Integration tests (real PostGIS)** — these encode the game rules:

- stranger's territory untouchable
- friend's territory protected during cooldown
- friend's territory stealable after cooldown
- **partial overlap carves rather than takes everything**
- re-running own land refreshes without double-counting
- adjacent claims both count
- steal writes a notification
- **no two active territories overlap** ← never delete this test
- upload is idempotent under a repeated `client_run_id`
- territory map is friend-scoped (a stranger sees nothing)

Use a separate throwaway test database on tmpfs, one transaction per test rolled
back afterwards, and a factory module that builds synthetic tracks in metres
relative to a **real** origin (not 0,0 — null island is a degenerate case that
hides latitude-dependent bugs).

---

## 10. Deliberately out of scope for v1

No Redis, no queue, no S3, no Kubernetes, no global leaderboard, no clubs, no
routes, no Strava import. One Postgres and one API process will carry this well
past the first few thousand users.

The things that will break first, in order:

1. **`ST_Intersects`** **against a growing territory table.** The partial GiST index handles the first phase. When it stops being enough, add an H3 cell column and filter on it before the geometry predicate — not a rewrite.
2. **Push notifications.** The outbox and devices tables should exist from the start; the APNs delivery worker is the highest-value missing piece.
3. **Urban GPS accuracy.** 20–50 m error between buildings means territory will not match the streets people ran. No backend work fixes this; the eventual answer is snapping to the OSM road graph.

---

## 11. Known open problems (do not pretend these are solved)

**Urban GPS error.** The number one thing likely to make users quit. Mitigated
but not solved by the accuracy filter and simplification.

**Suburbs beat cities.** Raw m² rewards whoever has the biggest blocks — a 5k
around four cul-de-sacs takes 400,000 m² while a 5k downtown takes 60,000. This
mostly washes out inside one friend group living in the same place, which is
another argument for friends-only early. If it bites, the metric becomes area
per kilometre run.

**Cold start.** The game is dead for anyone without three running friends
already on it. Onboarding must demand invites, not offer them. This is a product
problem and the hardest thing here.

**Rolling expiry vs monthly reset — unresolved.** Built as rolling; monthly is
one config flag away. Rolling means something is always about to lapse, so there
is always a reason to run today. Monthly creates a sprint-then-dead-week rhythm.
Genuinely different games.

**HealthKit / Apple Watch imports — unresolved.** An imported workout has no raw
fix stream, so anti-cheat layers 1–4 have nothing to inspect and only the pace
curve survives. Either accept weaker validation for imports, or stay
phone-tracked only and lose the Watch crowd.

---

## 12. How I want you to work

- **Write production code, not a demo.** Typed, layered, tested, with real error handling. No `TODO` stubs presented as finished.
- **Comment the** ***why*****, never the** ***what*****.** `# increment counter` is noise. "Without this, standing at a traffic light produces a hairball of micro-intersections" is the kind of comment that earns its place.
- **Prove the geometry before building anything on top of it.** If the loop extraction tests fail, nothing downstream matters.
- **Tell me when you are uncertain**, especially about the world-record values, and about anything you could not actually execute and verify.
- **Push back if a decision in this document is wrong.** Say so explicitly with your reasoning rather than silently substituting your own design.
- Be concise in prose. Put the detail in the code and its comments.