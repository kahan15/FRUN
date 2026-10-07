# Territory Run — laptop edition

Native SwiftUI iOS app + FastAPI + PostgreSQL/PostGIS. No hosted backend, paid map SDK, cloud database, analytics service, or subscription is needed for local personal testing.

**Version 0.3:** adds recoverable account deletion, privacy information and release configuration checks to the friend-scoped ownership/GPS/offline work. The full iOS Debug build and all 28 simulator XCTest cases pass, alongside 90 backend tests, 47 native Swift core checks and seven script regressions. Simulator sign-in, friend contests, partial captures, history and profile were checked with synthetic data. Automatic offline/reconnection behavior also passed. Remaining account/manual-retry UI checks and physical-device validation are still required. The October 4 hardening adds upload/geometry budgets, database timeouts, login spray limits, private-response handling and production configuration checks. Freeform capture now has dedicated unit and real-PostGIS regressions; [see the example and security-readiness report](docs/security-readiness-2026-10-04.md). The October updates fix database startup readiness, error-log privacy and four iOS compiler/test-target issues, sign-out choices and immediate manual sync, and verify the exact Docker stack. See [verification](docs/verification.md) and the [step-by-step App Store roadmap](docs/production-roadmap.md).

**October 5 daily-running update:** private weekly goals, GPS readiness/loop estimates and larger controls with finish review are now included. Progress stays on this phone and counts completed runs recorded since the feature was added. [Feature details and checks](docs/daily-features-2026-10-05.md).

## Start on your laptop

You need a Docker-compatible engine with Compose, Python 3, and an internet connection for the first dependency download. On a Mac, Docker Desktop is free for personal use under its current licensing terms. Containers and all application data then run locally. The supplied database image uses `linux/amd64`; Apple Silicon runs it under Docker's emulation.

```bash
cd territory-run
bash scripts/setup.sh
```

This generates unique local secrets, starts PostGIS, applies Alembic migrations, starts the API and expiry worker, and prints the phone's server address. Open [local API documentation](http://localhost:8000/docs). The readiness endpoint is [health/ready](http://localhost:8000/health/ready).

The database is persisted under `data/postgres/` on your laptop. Stop/start containers without deleting that directory:

```bash
docker compose stop
docker compose up -d db migrate api expiry
```

The laptop must be awake and the server running to sync. Runs continue recording away from the laptop and upload after reconnection. Both devices must be on the same trusted LAN for the default setup. No router port forwarding is needed or recommended. The development connection is HTTP; use it only on a trusted network. Release builds require HTTPS.

## Put it on an iPhone

The iOS build requires a **Mac with Xcode**, even if the backend runs on a Windows or Linux laptop. Use a current Xcode version that supports your installed iOS version; the app targets iOS 17 and later.

1. Open your installed Xcode (already installed and tested on this development Mac). For physical-device signing, add your Apple account in Xcode Settings → Accounts yourself. Use Apple’s official downloads when installing on another Mac.
2. Open the included `ios/TerritoryRun.xcodeproj`.
3. If you change `ios/project.yml`, install XcodeGen and regenerate with `bash scripts/ios-setup.sh`.
4. In the generated Xcode project, select the TerritoryRun target. Under Signing & Capabilities, choose your **Personal Team**. If needed, change the bundle identifier to a unique identifier in `ios/Config/Local.xcconfig` and regenerate the project.
5. Connect your iPhone, enable Developer Mode when prompted, select it as the run destination, and press Run. Use the Debug configuration. A simulator also works for UI checks.
6. On the sign-in screen, enter the laptop address printed by the setup script. On a simulator running on the same Mac, use `http://localhost:8000`.
7. Create an account. Press Start to request location access, record a closed loop, and Finish. If Motion permission is declined, GPS tracking still works.

A free Personal Team supports personal device testing but its provisioning expires after **7 days**, requiring a rebuild/reinstall. TestFlight/App Store distribution and optional APNs push require Apple program enrollment/capabilities. **No enrollment or paid service has been purchased or enabled.**

Apple's current terms: [personal-team limits](https://developer.apple.com/help/account/basics/about-your-developer-account/), [membership and personal-device testing](https://developer.apple.com/help/account/membership/program-enrollment/). Docker's terms: [Docker Desktop license](https://docs.docker.com/subscription/desktop-license/).

## What is implemented

- Delete account with password confirmation, server-side removal and session revocation, plus recovery after a lost response. Backup dumps need separate retention and restore reconciliation before production.
- Register/sign in; Argon2 password hashing; short-lived access tokens; rotating refresh tokens; Keychain storage; logout and laptop-admin password reset.
- Start/pause/resume/finish, background GPS, accuracy filtering, CoreMotion steps, a disk journal for interrupted runs, account-and-server-isolated offline queues, replay-safe upload IDs, and cached territory overlays.
- Server-side loop extraction, supported-extent checks, record-inspired pace checks, stride flags, and an audit trail.
- Independent overlapping ownership for non-friends; accepted-friend visibility/capture only; contested overlaps on acceptance; partial contest settlement, friend cooldown, scoped own-land renewal, server-ordered claims, rolling expiry, and configurable monthly boundaries.
- Friend requests/accept/remove, username search, friend leaderboard, current/past GeoJSON API, run history with pagination, stats, and an in-app theft feed.
- Optional APNs worker with retry/backoff and per-device delivery records. It is disabled by default; the in-app feed works without it.
- Local backup, restore, storage report, API docs, health endpoints, bounded request bodies, authentication/upload throttles, and migration/test commands.

## Verify before relying on it

```bash
bash scripts/test.sh
bash scripts/smoke-test.sh
```

This uses `compose.test.yaml`, with a separate Compose project and disposable tmpfs PostGIS database called `territory_test`. It needs no app `.env` or running development database. It runs unit tests, migration rollback/forward, real spatial claims, API checks, and simultaneous claims. It does not use your running app's data. Tests deliberately refuse another database name. Each invocation uses its own Compose project. The smoke runner layers compose.smoke.yaml on the isolated test configuration and verifies migrations, actual Uvicorn HTTP readiness, authentication and recoverable deletion. Neither runner publishes a host port or reads the app's .env/data; cleanup removes only that run's synthetic resources.

For just the fast backend suite without Docker:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
python -m pytest -m 'not integration' -q
```

For iOS, open the included project, select an iPhone simulator, and use Product → Test in Xcode. The included 28 XCTest tests cover wire-format compatibility, timestamps, map holes, GPS continuity, journal crash recovery, upload isolation, and token refresh. `bash scripts/check-ios-core.sh` runs 47 shared-code checks with native Apple frameworks without XCTest. `bash scripts/test-ios-core.sh` runs the XCTest package on a Mac with a working SwiftPM/XCTest toolchain. Run the [device acceptance checklist](docs/device-checklist.md) before using the app for important runs.

## Keep your data

```bash
bash scripts/backup.sh
bash scripts/storage.sh
```

Backups are local PostgreSQL dumps under `backups/`. Copy them to an external drive. Keep `.env` separately protected; it contains the password and JWT signing key. To restore an existing dump, use `bash scripts/restore.sh backups/FILE.dump`; that script explicitly asks before replacing the current database.

Do not delete `data/`, uninstall the iPhone app while it holds unsynced runs, or treat files on the same laptop as disaster recovery. iPhone files are excluded from iCloud backup; credentials use a non-synchronizing, device-only Keychain accessibility class.

## Ownership in this version

Only accepted friends see and capture one another's land. Non-friends (including pending requests) can own the same area independently; their land never blocks your claim. There are no separate competitions.

Accepting a friend preserves both holdings and marks their overlap purple as **contested**. The first server-processed qualifying run that started after acceptance wins only its captured portion, immediately bypassing ordinary protection there. A mutual friend can settle land held by both friends; someone who is not friends with both cannot see that contest. Older offline runs cannot settle it. The winning slice gets fresh protection; the unvisited remainder stays contested.

Removing a friend ends visibility and capture permission and removes that pair's contest. Reacceptance contests any overlap that exists then. Renewal extends only the portion actually captured and does not restart ordinary protection. The backend serializes claims, friendship changes, and expiry in one transaction order.

## Update an existing laptop install

Back up first with `bash scripts/backup.sh`. Keep your existing `.env`, `data/`, `backups/`, and `secrets/`. Replace the source files, then run `bash scripts/setup.sh` to rebuild locally and apply migrations through `0003`. The migrations preserve existing ownership and add contest records and recoverable deletion receipts. A rollback to the old schema refuses independent overlaps instead of deleting anyone's land.

The generated Xcode project uses the existing local configuration. No Apple membership, hosting, or push service was purchased or enabled.

## Change game settings

Edit `.env`, then run:

```bash
docker compose up -d --force-recreate api expiry
```

The defaults are 30-day rolling ownership, six-hour capture protection, 30 m loop closure, 4 m simplification, and a 200 m² jitter floor. Renewal changes expiry without extending capture protection. `MONTHLY_RESET=true` gives newly claimed/refreshed territories the next UTC month boundary; changing this flag does not retroactively rewrite existing expiry dates.

See [decisions.md](docs/decisions.md) for deliberate specification corrections and [operations.md](docs/operations.md) for local maintenance, optional push, and troubleshooting.

## When to spend money

There is no automatic cloud migration. Use measured disk growth, backup time, laptop uptime, and sync reliability to make that decision. Disk space is only one constraint: friends outside your LAN cannot sync with the default setup, even if the laptop has plenty of room. Keep this release local, and make remote access or paid distribution a separate decision when needed.

Native Apple maps may need internet for new map tiles. “No cloud backend” means your accounts, GPS tracks, territories, and game events are stored by this app on your laptop and temporarily on phones; it does not make Apple's basemap service fully offline.

## Release preparation

`bash scripts/ios-preflight.sh` checks full Xcode/iOS SDK availability. `python3 scripts/check-release.py` checks Release settings and intentionally fails until real public HTTPS URLs, signing identity and a unique bundle identifier are supplied. `python3 -m unittest discover -s scripts/tests -v` tests that validator. Release builds run it automatically with expanded Xcode settings and an SDK check. Keep local development on Debug.

The owner has chosen individual publishing under their legal name and a free first release without ads or paid features. Spending and enrollment remain unapproved. Follow [production-roadmap.md](docs/production-roadmap.md) for the exact next owner actions, engineering gates, TestFlight and App Review steps.
