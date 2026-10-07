# Physical test evidence — fill in after execution

Date: pending
Phone model: pending
iOS version: pending
Xcode version: pending
Build/configuration: pending
Server version/address: pending
Location permission / precise location: pending
Motion permission: pending
Battery start/end and elapsed time: pending

| Scenario | Pass/fail/not run | Observations / run UUID / error |
| --- | --- | --- |
| Simulator Debug build and XCTest | Passed | 18 cases rerun successfully 2026-10-03; Xcode 26.3, SDK 26.2, iPhone 17 / iOS 26.3.1. See testing-2026-10-03.md. |
| Physical iPhone signed build / launch | Not run | |
| Manual simulator sign-in / map / profile | Passed | Synthetic account, native map, stats and sync verified; see October 3 report for scope. |
| Simulator friend acceptance / partial contest / history | Passed | Synthetic overlapping loops; stranger remains independent; partial capture replay has one receipt. |
| Simulator cached map / automatic API reconnection | Passed | Offline retains overlays; API restart restores Synced without another sign-in. |
| Corrected sign-out / immediate retry / deletion UI | Not complete | Simulator tab-bar input failed; manual owner steps in October 3 report. |
| 15–30 minute locked-screen run | Not run | |
| Background in another app | Not run | |
| Approximate/denied location and denied motion | Not run | |
| Pause, GPS gap, resume without connecting gap | Not run | |
| Offline Finish, restart, reconnect, exactly one receipt | Not run | |
| Interrupted active run recovers paused | Not run | |
| Stranger overlap, accepted-friend contest, partial win | Not run | |
| Third-party privacy, removal and reacceptance | Not run | |
| Wrong password and successful account deletion | Not run | |
| Lost deletion response and cleanup after restart | Not run | |
| VoiceOver and large text | Not run | |
| Public Release endpoints on cellular (later) | Not run | |

Do not mark a scenario passed without running it. Record unexpected behavior and the exact checklist step.
