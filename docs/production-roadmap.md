# Territory Run: next steps to App Store production

Updated October 5, 2026. Individual publishing under your personal legal name; free app, no ads or paid features. Development stays on the laptop. No enrollment, hosting purchase, public deployment or App Store upload has been approved or performed.

The approved weekly goals, GPS/loop guidance and running controls are implemented. The final Debug build and **28 iOS XCTest cases** passed; **47 native Swift core checks** and **7 script checks** passed. Backend source is unchanged since its **90-test and runtime-smoke pass on October 4**. See [feature details](daily-features-2026-10-05.md), [verification](verification.md) and [security readiness](security-readiness-2026-10-04.md). This is not a production-ready certification.

## 1. Immediate next step: real-iPhone acceptance

Xcode is already installed at `/Users/kj_lomran/Downloads/Xcode.app`; the existing project is `ios/TerritoryRun.xcodeproj`. You do not need another Xcode download for the current local checks. Command-line simulator access is restricted in the agent environment; normal Xcode builds/tests work. Do not disable macOS protections or reset the simulator to work around that restriction.

### **PRIVATE DATA AND LOCAL NETWORK NOTICE**

The following device test records real location on your phone and uploads it to your laptop when connected. Accepted test friends can see captured territory. Use a safe test route and deliberately selected test accounts; keep home/work locations out of screenshots you share. The local development API uses HTTP on your trusted Wi-Fi and is reachable by devices on that network. Do not use public Wi-Fi, router forwarding, public tunnels or upload real routes here. Apple sign-in and map services involve Apple; enter credentials yourself. No new paid service is needed for these local checks.

1. Open Docker Desktop and wait for it to finish starting. In Terminal, `docker info` and `docker compose version` must succeed. Do not use factory reset or delete existing volumes.
2. Open Terminal and enter `cd /Users/kj_lomran/Desktop/FRUN/astra/territory-run`. If an app database already exists, run `bash scripts/backup.sh` first and keep `.env`, `data/`, `backups/` and `secrets/`. Then run `bash scripts/setup.sh`. Setup rebuilds the local service and applies migrations; inspect errors instead of deleting data to retry. Ask for assistance if your existing Docker credential helper blocks setup.
3. Save the printed iPhone server address, for example `http://192.168.1.20:8000`. Keep the laptop awake and both devices on the same trusted Wi-Fi. The simulator's old `127.0.0.1:8001` address belongs to a disposable test server that is no longer running; it is not the physical phone's server address.
4. In **Xcode → Settings → Accounts**, sign in with your Apple Account yourself. Do not share passwords, verification codes or signing keys. Do not buy membership yet.
5. Connect and unlock the iPhone. Review its Trust and Developer Mode prompts yourself. In Xcode select **TerritoryRun target → Signing & Capabilities → Personal Team**. If necessary, choose a unique `APP_BUNDLE_ID` in `ios/Config/Local.xcconfig`. Select your physical iPhone as destination, keep **Debug**, and press **Run**. Reinstall over the app; do not uninstall an app holding unsynced runs.
6. On the phone sign-in screen, enter the laptop's printed LAN address and use a test account. Allow the app's expected Local Network and location prompts. Use Precise Location. Motion access is optional. Do not accept unrelated permission prompts.
7. On **Run → weekly goal**, choose **Active days → 1 → Save**. Reopen it to confirm the setting; change to 5 and verify persistence, test Cancel, then choose your preferred goal. Also test a distance goal. Completed running totaling at least 100 m in a day should count once; goals reflect this phone's recordings, not older server history.
8. Outdoors, tap **Check GPS**, wait for **GPS ready**, and record an irregular loop for 15–30 minutes without pausing. Lock the screen for at least ten minutes. Finish near the start. Review the path, final server result, elapsed time and battery change. A loop preview is an estimate, not an award. Do not infer battery reliability from one short run.
9. In a separate run, tap **Finish → Keep running** and confirm recording continues. Test **Pause → Resume**: guidance should begin a new segment and never connect the gap into captured land. Confirm Finish only when ready.
10. Turn Wi-Fi off, finish and save, then close/reopen the app without uninstalling. Confirm the queued run survives. Restore the same Wi-Fi and laptop connection; verify one history record, one capture result and no doubled weekly distance. Use Wi-Fi for this check; carrier data costs are outside this test plan.
11. Test permission revocation, temporarily disabling Precise Location, and recovery of an interrupted active run. Previously saved points must remain; recovery should pause and never invent missing GPS. Repeat with the phone's largest Accessibility text size and VoiceOver. All controls, goal settings and finish choices must remain reachable and clear. Return settings to your preferences afterward.
12. Test deletion and wrong-password rejection only with a deliberately disposable account after reviewing what will be erased. The app requires explicit confirmation. Never delete your real account or unsynced runs merely to test this.

Record outcomes in [iPhone evidence](device-evidence.md) and the [device checklist](device-checklist.md). Report device/iOS version, duration, battery change, observed behavior and error codes; you do not need to send private route coordinates. Personal Team provisioning is temporary; Apple's [account overview](https://developer.apple.com/help/account/basics/about-your-developer-account/) explains its limits.

**Exit:** repeatable passing physical tests, no lost/duplicated runs, usable large-text/VoiceOver controls, and resolved account/deletion/manual-sync UI checks. We must fix and retest failures before proceeding.

## 2. Finish the public-beta engineering gates

I can implement and test these locally after the relevant product policies below are approved. They do not require buying hosting first.

| Work | Required result |
| --- | --- |
| Recovery and email ownership | Expiring, single-use, throttled recovery/verification; no account enumeration; sessions revoked as appropriate. Use a local delivery fixture until a real delivery service and its cost/data destination are approved. |
| Blocking/reporting and moderation | Agreed rules for blocked users, invitations, discoverability and existing territories; authenticated reports and an operator workflow; tests for permission bypass. |
| Retention and account deletion | Agreed raw-route/backup retention, protected export if required, purge behavior and deletion-aware restoration. Restoring a backup must not resurrect deleted accounts. |
| Database access | Separate migration and least-privilege runtime roles, tested on disposable databases. Development's database user is not a production privilege model. |
| Failure/capacity drills | Agree an initial runner/concurrency target; test load, slow uploads, locks, DB/network outages, interrupted uploads, disk pressure, backup restore and deployment rollback. |
| Release/security checks | Review dependencies and image advisories, authorization boundaries, secrets, input budgets and privacy logging; address findings and rerun the affected suites. |
| Operations | Actionable health/error/storage alerts, encrypted off-machine backups, verified restores, deploy/rollback procedure and a support/incident plan. Production-sized evidence is required later. |

These are gates, not guarantees that outages or GPS spoofing can never happen. The existing bounds and tests reduce specific risks; they do not replace real capacity measurements and operational drills.

## 3. Product/privacy decisions you must approve

Before those flows are finalized, approve the app's public name, initial countries and intended minimum age; support contact; raw-route and backup retention periods; account verification/recovery method; blocking/reporting behavior; and an initial scale target. I will present concrete defaults and explain the tradeoffs instead of silently choosing policies that expose or delete users' data.

Weekly goals are currently private to each phone. Cross-device goal syncing would be a separate product/data-sharing change. Unapproved suggestions 2, 3 and 5 (reminders, spoken updates, progress charts) remain unimplemented.

## 4. Hosting and Apple membership — only after explicit approval

### **FUTURE COST AND PUBLIC DISCLOSURE — PAUSE FOR APPROVAL**

Public production needs an available HTTPS backend beyond a sleeping laptop. Hosting, database backups, a domain and message delivery may incur charges; no provider or price has been selected. Before any purchase or data transfer, I will give you the exact provider, data destination/region, monthly limit, expected extras, renewal terms and rollback plan and wait for approval. Development can remain laptop-local after a separate production service is approved.

Apple currently lists **US$99 per membership year**, with regional pricing/taxes and renewal terms. Individual publication makes your **personal legal name public as the seller**. Do not enroll or pay until you explicitly choose to proceed. [Apple enrollment and fees](https://developer.apple.com/help/account/membership/program-enrollment/) (checked October 5, 2026).

When ready, you enable two-factor authentication on your Apple Account, visit [Apple enrollment](https://developer.apple.com/programs/enroll/), choose Individual, verify identity, review the agreement/fee and complete payment yourself. Later provide only the Team ID and chosen bundle identifier when needed, not credentials, payment details or private signing keys.

**Exit:** approved production budget/data destination, active membership and a tested HTTPS service with protected database/backups. Signing or making an archive does not itself authorize uploading it.

## 5. Release candidate and TestFlight

1. Configure real HTTPS API/privacy/support URLs, unique bundle ID and Apple Team ID in Release settings. Run `python3 scripts/check-release.py`; its current failure on unset production configuration is intentional. Confirm no development endpoints or secrets enter the archive.
2. Recheck Apple's SDK requirement before upload. The current rule requires Xcode 26+ and an iOS 26+ SDK; the device minimum can remain iOS 17. [SDK requirement](https://developer.apple.com/news/upcoming-requirements/?id=04282026a).
3. Test the signed release against the approved production service from outside the laptop LAN, including recovery/deletion and the full offline matrix. Any cellular charges need your approval. Verify the app works while the laptop is off.
4. Prepare the App Store Connect app record, privacy answers, age rating, export-compliance answers and support/privacy pages. Review what will become public before publishing pages or the listing.
5. In Xcode select a device/archive destination, **Product → Archive**, then validate the archive. Pause before **Distribute App → App Store Connect → Upload**: uploading the build to Apple is a separate explicit approval.
6. After approval/upload, review processing warnings and test internally. With your approval, invite a small trusted group (suggested 5–10 runners over about two weeks) through TestFlight and complete any beta review. This group size/duration is our test plan, not an Apple requirement. [Apple external testing workflow](https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers/).

**Exit:** no open critical acceptance failures, measured battery/recovery results across more than one device/OS, passing release gates, tested backup restoration and an operating support/monitoring process.

## 6. App Review and controlled launch

Prepare actual screenshots of the final app using synthetic profiles/territories; approve the description, age rating, privacy disclosures and public contact information. Give Apple a dedicated reviewer account containing no private runner routes and clear instructions for friends, capture, GPS/offline behavior and deletion. Keep the backend working throughout review. [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

Choose manual release in App Store Connect. Pause for your approval before submitting the reviewed build/listing, and again before public release after acceptance. Address review findings, retest any changes, and monitor errors, upload delays, database growth and support after launch. Keep a rollback plan available; a launch is not the end of maintenance. [Submission workflow](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app/).

The updated ZIP is editable source, not a signed App Store archive. The immediate action remains section 1: physical iPhone acceptance. No purchase is needed to complete that local stage.
