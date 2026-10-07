# First device acceptance run

Use a small walking/running loop in a safe place. Test with throwaway accounts first.

1. Start the backend and run `scripts/test.sh`. Do not continue to trusting real claims if the ownership or migration tests fail.
2. Open the included Xcode project (regenerate only after editing project.yml). Build the Debug app and run the included XCTest suite. The 18 cases passed on the development simulator on October 2; rerun for a changed candidate. Confirm the API contract decodes `new_area_m2`, `client_run_id`, fractional timestamps, and MultiPolygon holes.
3. Register two accounts on two devices/simulators against the same laptop. Request friendship from A and accept from B. Confirm each sees only the accepted friend and themselves in the leaderboard.
4. On a physical iPhone, press Start and allow location. Wait for usable GPS accuracy. Record a loop larger than 200 m² and finish within 30 m of its start. Confirm a result and an overlay after upload.
5. Start another run; lock the phone screen for several minutes while moving. Unlock, finish, and confirm the background segment exists. Simulator checks are not a substitute for this step.
6. Stop the laptop API (`docker compose stop api`). Finish a run. Confirm the queue says it is saved. Force-close and reopen the app: the queued run must remain. Restart the API (`docker compose start api`) and Sync: one result and one run row must appear.
7. Repeat Sync and relaunch. Area must not increase a second time from the same uploaded UUID.
8. Interrupt an active run by closing the app. Reopen. It should recover paused with the previously saved points. Resume after moving elsewhere: no imaginary connecting line or territory edge should be added.
9. Run an out-and-back: get no enclosed territory. Pause before crossing a gap: the gap must not close a loop.
10. Run the same owned loop again: area stays constant and expiry moves forward. A shared border alone does not count as overlap or refresh.
11. In a disposable test database, shorten `COOLDOWN_HOURS` to exercise theft. B should take only the overlapping part of A's polygon, and A should see a feed entry. Restore the six-hour default afterward.
12. Before accepting friendship, let A and B each capture the same area: both own it, neither sees the other, and neither is blocked. Accept the request: both maps show the overlap as purple contested land. A new qualifying run across half wins only that half immediately. The remainder stays contested; an old queued run cannot settle it. Remove the friendship: visibility and capture stop, and subsequent non-friend captures remain independent. Reaccept: the current overlap becomes contested again. Repeat with C friends with only A: C must not see B or their contest.
13. Sign out with a completed queued run. Sign into another account: its queue must be empty. Sign back into the original account and original server address: the run must remain available.
14. Verify Motion denial still permits GPS recording and an accepted run; confirm bad GPS makes the visible result explain the failed check.
15. Create a backup, restore it into a disposable copy, and confirm users, tracks, claims, and feed survive. Never use the only live copy to rehearse restore.

Document the iPhone model, iOS version, Xcode version, permission choices, and any failed step. Those observations are required before claiming the app is verified end to end on hardware.

16. Disable Precise Location, then Start. Confirm the precision prompt/message appears. Reenable it, start again, lock the screen for 15–30 minutes, and check point continuity, battery use, and the background indicator on a real iPhone.
17. Simulate a delayed GPS batch, a >30-second outage, and inaccurate samples. Delayed good samples are retained; outages and inaccurate spans never connect into a loop.
18. Terminate immediately after Finish saves the queue but before active-file cleanup. Reopen: one pending run, no active duplicate. Interrupt after server commit but before receipt; reconnect and verify the same server result.
19. Test one unreadable queue file plus one good upload. The issue remains visible and preserved; the good run uploads. A server 422 preserves that upload under needs-attention; the Retry held uploads button requeues it after fixing the underlying issue.
20. Disconnect the API during an upload. Observe bounded retries; bring it back with the app active and confirm recovery. If iOS suspended the app, reopen it and confirm sync resumes. No force-quit/background-upload guarantee is implied.

21. Wrong-password account deletion preserves account/server records/local files. Correct-password deletion removes that account's data and rejects old sessions; a second account's earned territory survives without identifying history references. Use throwaway data.
22. Cut network access during deletion and reopen. Pending deletion prevents new recording/uploads; local runs remain until the server confirms. Retry status after reconnect. Test a crash after server completion but before local cleanup; reopening must finish cleanup without requiring a live session.
23. Confirm Privacy and data is accessible both before registration and under You. In a configured Release build, open the real privacy/support URLs and verify no development server address field appears.
24. Test VoiceOver labels, large text, offline errors and destructive confirmation on the smallest and largest supported iPhone screen sizes.
