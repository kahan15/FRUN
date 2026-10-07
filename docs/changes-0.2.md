# Territory Run 0.2

- Replaced global exclusivity with independent non-friend ownership. Pending requests grant no map/capture access.
- Added migration 0002: accepted friendship timestamps, pairwise contested geometry, and a friend-aware database guard. Existing holdings are preserved.
- Acceptance contests existing overlaps. The first qualifying run started afterward settles only its captured part; older queued runs cannot settle it. Ordinary six-hour protection remains elsewhere, and winning slices receive fresh protection.
- Added purple contested MapKit overlays and typed API geometry. Removing/reaccepting friendship clears/recreates that pair's contest.
- Renewals now extend only captured own land. Geographic stolen totals avoid double counting multi-owner contested land.
- Kept native Apple maps/location services. Preserved delayed GPS batches, precise-location checks, gap/accuracy segment breaks, durable synchronized journals, and paused recovery after interruption.
- Hardened offline queues: stable payloads and UUIDs, matching receipts, active-draft reconciliation, account/server isolation, bounded retry backoff, short background execution time, and recoverable held uploads.
- Added 19 real PostGIS integration tests in the 57-test backend suite, 16 XCTest cases, a 24-check native Swift executable, an isolated test Compose file, and an included generated Xcode project.

Open `ios/TerritoryRun.xcodeproj` in Xcode for device/simulator work. Back up an existing laptop database, retain `.env` and `data/`, and run `bash scripts/setup.sh` to rebuild and migrate locally. No hosting or Apple enrollment was purchased. Read `verification.md` for the completed checks and remaining hardware gates.
