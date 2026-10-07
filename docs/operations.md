# Laptop operations

## Daily use

Run `bash scripts/setup.sh` for first setup, and keep Docker running. The laptop can sleep while you run; the phone retains the run and syncs when you return to the same network. iOS may stop a force-quit app from receiving location updates. The app recovers previously journaled points, pauses the recovered run, and never invents missing GPS.

The app retries the queue on launch, foregrounding, network restoration, every 30 seconds while open, and manual Sync. Queues are isolated by server address and user ID. Use the same server address consistently: changing from an IP address to a hostname creates a different local namespace. Use a DHCP reservation or stable `.local` hostname for the laptop. When reinstalling with free signing, rebuild over the app; deleting it removes unsynced files.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| iPhone cannot register/sign in | Same Wi-Fi; use laptop LAN IP, not `localhost`; allow Local Network permission; allow inbound 8000 in the laptop firewall on this trusted network. Guest Wi-Fi may isolate devices. |
| Server not ready | `docker compose logs --tail=100 db migrate api`; run `docker compose ps`. |
| Run records but cannot upload | Laptop asleep/disconnected or server stopped. Leave the completed run in the queue and retry. |
| GPS stops with screen locked | Allow location permission, verify background location mode, test outside with a physical device. Avoid force-quitting the app. |
| App stopped launching after a week | Rebuild and install from Xcode; free signing expires after seven days. |
| No territory from a visible loop | Inspect result reasons, pause/GPS gaps, closure distance, and the 200 m² noise floor. |
| No new area | Look for renewed land or protected ground in the result. |
| Password forgotten | Reset it locally with the command below; no email service is required. |
| Database password changed in `.env` | Editing `.env` does not change an initialized PostgreSQL role password. Restore the original secret or alter the database role deliberately; do not delete `data` as a workaround. |

## Audit and password recovery

```bash
docker compose exec api python -m app.workers.admin audit
docker compose exec api python -m app.workers.admin replay RUN_UUID
docker compose exec api python -m app.workers.admin review RUN_UUID 'Reviewed GPS interruption with runner'
docker compose exec api python -m app.workers.admin password USERNAME
```

Password input is interactive and does not appear in shell history. Reset revokes existing sessions. Replay reports the current anti-cheat verdict without mutating awarded geometry; review notes are saved separately.

Disable new registration by setting `REGISTRATION_ENABLED=false` in `.env` and recreating the API container. There is no email verification in the laptop edition; treat it as a closed personal test installation.

## Backups and storage

`scripts/backup.sh` makes a transactionally consistent custom-format PostgreSQL dump. `scripts/restore.sh` is intentionally destructive and prompts before replacing the local database. Restore stops game writers and uses one transaction; on a restore error it leaves writers stopped for inspection. A healthy restore restarts API and expiry; optional push stays stopped.

`scripts/storage.sh` shows database/table size and laptop free space. Docker images and local backups also occupy space. Containers rotate logs. No user data is deleted automatically.

Use actual measurements after a week of runs to estimate growth. For example, subtract the database size before and after a known number of runs to estimate bytes/run, then multiply by expected runs per month. Decide retention or additional storage before the disk fills. Keeping a laptop awake for other users can become a reliability problem earlier than storage becomes a problem.

## Optional APNs — only when you choose it

The personal zero-purchase build intentionally has no APNs entitlement. Once you decide to enable paid Apple capabilities:

1. Configure your Apple developer team and a push-capable App ID in Xcode and Apple Developer. Do not commit the private key.
2. Place the `.p8` key in `secrets/AuthKey.p8` on the laptop and make it readable by the worker container user (UID 10001). Mount is read-only.
3. Set `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_TOPIC` (matching the bundle ID), `APNS_KEY_PATH=/run/secrets/AuthKey.p8`, and the appropriate `APNS_SANDBOX` value in `.env`.
4. In your XcodeGen target add an entitlements file with the appropriate `aps-environment`, enable Push Notifications for signing, set `PUSH_ENABLED=YES`, regenerate, and install that signed build. Debug development tokens use sandbox; distribution tokens use production.
5. Run `docker compose --profile push up -d push`.
6. In the app's profile, choose Enable push alerts. The token is registered for the signed-in account. Theft events already appear in the feed regardless of push delivery.

Apple documents [capability setup](https://developer.apple.com/help/account/identifiers/enable-app-capabilities/). Push sends notification text and identifiers to Apple's delivery infrastructure; keep it disabled if you want a strictly local application backend with no push egress.

## Before external users

Run the database and device gates. Complete a pace-record review, account deletion/export, email ownership/recovery decisions, HTTPS and remote connectivity, and abuse controls suited to your audience before public release. These are release work, not reasons to buy hosting now. No provider is chosen automatically.

## Runtime bounds and production safeguards (October 4)

The defaults in `.env.example` bound upload body duration, database connection/pool waits, statements, locks and idle transactions. Database-busy responses use HTTP 503 so saved iOS uploads can retry. The runtime caps Uvicorn concurrency at 32. Measure the real deployment before changing limits; never disable bounds merely to hide overload.

Route processing rejects more than 10,000 simplified vertices or 20,000 edge intersections before noding. The original run remains saved with `route_too_complex`, and no land is awarded. Four-metre simplification, 30-metre endpoint closure and the 200 m² noise floor otherwise remain unchanged. The route shape is never replaced with a rectangle or convex hull.

`ENVIRONMENT=production` requires explicit JSON `ALLOWED_HOSTS` (include the approved API hostname and localhost for the container healthcheck) and a freshly generated strong JWT secret. Wildcards, obvious placeholder secrets and unknown environment names fail startup. API docs are disabled in production. The development Compose setup remains local mode; switching the environment does not configure TLS, proxy trust, least-privilege database roles, monitoring or backups. Complete the [security-readiness gates](security-readiness-2026-10-04.md) before public use.
