# Daily-running features — October 5, 2026

The owner approved features 1, 4 and 6. They are implemented in the existing native iOS project. No paid service, new server, enrollment or public upload was used. Backend ownership behavior is unchanged.

## Weekly goals (1)

- Open the goal card on Run or the Weekly goal section under You. Choose distance (1–200 km) or active days (1–7), adjust the target, and Save. Goals start unset; they can be changed or turned off.
- The ring uses Monday–Sunday in the phone's current time zone, including daylight-saving changes. A day counts after at least 100 m of completed running, allowing short runs to add together. Rest days do not reset a streak because there is no streak penalty.
- Progress counts completed runs saved on this phone since this feature was introduced, including existing readable pending uploads. It does not import historical server receipts or synchronize goals between devices. This scope is explained in the goal editor.
- Run UUIDs prevent double counting during retries. The original start date determines the week; uploading late does not move a run into a new week. Paused or lost-GPS gaps add no distance.
- Settings and summaries use the existing protected account-and-server-specific folder and are excluded from iCloud backup. Sign-out clears memory, while confirmed account deletion removes the folder. No extra GPS trace is saved for this feature.
- Goal storage failure is visible and does not block recording or uploads. Corrupt goal files are preserved; progress is marked potentially incomplete instead of silently replacing the file.

## GPS and loop guidance (4)

- Check GPS runs a foreground-only, up-to-20-second check without saving a route. It ends on leaving Run or backgrounding the app. Fresh accurate GPS is distinguished from weak, stale or unavailable samples.
- During recording, distance-to-start refers to the current uninterrupted segment, not a straight line across a pause or signal gap.
- A simple enclosed route near its start can show a mint dashed estimate. Inward bends are preserved. Open, tiny, crossing or excessively complex previews are withheld; the final server can still process valid separate loops.
- The estimate uses the current 30 m closure / 4 m simplification / 200 m² defaults. It is explicitly an estimate: server settings, GPS validation, friend ownership and capture protection determine actual awards. It never changes server ownership.
- Preview processing has a bounded simplification work budget and a maximum of 400 preview vertices. Real outdoor performance and battery use still require device acceptance.

## Running controls (6)

- Larger Start, Pause/Resume and Finish controls have at least 60-point content height, Dynamic Type layout fallbacks, accessible labels/hints and stable test identifiers.
- The bottom panel scrolls so larger content remains reachable. Running focuses on distance and active time; weekly goals appear when idle.
- Finish opens a separate review with Finish and save run / Keep running. Recording continues until confirmation. Cancelling or dismissing the review does not finish the run.
- Duplicate finish calls are guarded. Once the run is durably queued, the next run need not wait for a network request. The ordinary offline queue still handles upload recovery.
- Privacy and data explains the temporary GPS check and local weekly progress.

## Verification and honest limits

- Full Debug iOS app/test build succeeded; **28 XCTest cases passed**, zero failures and no recorded build/test issues. Ten new cases cover weekly boundaries, DST, retry/account isolation, damaged files, stale GPS, concavity, crossing paths and segment gaps. [Xcode evidence](test-results/2026-10-05/ios-xctest-summary.json).
- **47 native Swift core checks passed**, including 16 new goal/guidance checks. [Output](test-results/2026-10-05/swift-core.txt).
- **7 script checks passed.** [Output](test-results/2026-10-05/script-checks.txt).
- Backend files were unchanged in this feature pass. The latest backend evidence remains **90 tests and runtime smoke passed on October 4**; it is not relabelled as a new run.
- Simulator screens were visually inspected: idle goal card, goal editor, running controls, pause state and finish review. Check GPS reached GPS ready; stale GPS returned to Waiting. Keep running left recording active; Pause/Resume retained elapsed time; confirming Finish produced one saved offline run.
- Coordinate input to Simulator failed in the automation tool, so picker/toolbar Save and largest-text/VoiceOver checks remain manual. Goal storage behavior was verified by XCTest and native checks. Those checks are not a substitute for the final UI acceptance steps below.
- The final UI wording hides GPS readiness while paused and calls the timer Active time. These refinements are included in the final Xcode verification.
- One disposable zero-distance simulator run remains queued in the existing synthetic account because its temporary October 3 server is offline. No real user data or existing Docker resources were deleted. No actual captured route, backend reconnection or battery result is inferred from that empty run.

## Quick owner acceptance

1. On Run, tap the weekly goal card. Select Active days, increase to 5, Save, then reopen and check that 5 was retained. Test Cancel without changing the saved target. Try Distance too.
2. Check GPS outside, start a real test run and close an irregular loop without pausing. Compare the mint estimate with the final capture after syncing.
3. During a separate run, tap Finish → Keep running. Confirm the timer continues; then Pause → Resume and check that a fresh segment begins.
4. Turn Wi-Fi off, Finish and save, relaunch without uninstalling, and verify the queued run survives. Reconnect to the laptop server and verify one history record and no duplicated weekly distance.
5. Test the largest Accessibility text size and VoiceOver on the device. All controls must remain reachable; review and cancel must be clear. Return settings to your preferred values afterward.

Follow the [production roadmap](production-roadmap.md). No public-production readiness certification is implied.
