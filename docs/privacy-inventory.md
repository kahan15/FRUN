# Privacy inventory — development version 0.3

This is an implementation inventory for preparing accurate disclosures. It is not the final public privacy policy. Owner identity/contact, countries, audience, retention periods, hosting and deletion-aware backup restore remain open release decisions. Review the final implementation before approving App Store Connect answers.

| Current collection | Stored where | Current purpose / visibility | Manifest category |
| --- | --- | --- | --- |
| Display name | Server account | Profile, discovery and friend UI | Name |
| Email address | Server account | Login identity; currently no email delivery | Email Address |
| Username, account ID, password hash and sessions | Server; tokens in device-only Keychain | Authentication and access control | User ID / account information |
| Precise GPS samples, times, accuracy, territory geometry | Phone journal/queue; server raw upload and geometry | Recording, validation and claims; raw track not exposed to friends | Precise Location |
| Duration, distance, optional motion step count | Phone and server | Exercise recording/validation | Fitness |
| Accepted/pending friend relationships | Server; phone friend list in memory | Social access control; no system address-book access | Contacts (social graph) |
| Capture results, territory and run history | Server; phone cache/receipts | Game progress | Gameplay Content |
| Optional M/F/X pace-check choice | Server account | Pace validation; not in public profiles | Other Data Types |
| Pseudonymous deletion hashes and completion time | Server account_deletions | Lost-response recovery and future restore reconciliation | Account information; not asserted to be anonymous |

The bundled manifest marks listed account-linked collection as **App Functionality**, **linked to the user**, **not used for tracking**. There is no advertising SDK, cross-app tracking or third-party analytics SDK. UserDefaults stores app-owned values, declared under required reason **CA92.1**. Verify the archive's generated privacy report, not only this source file. [Apple manifest data types](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacycollecteddatatypes/nsprivacycollecteddatatype), [required API reasons](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitypereasons).

APNs is disabled. If enabled later, reevaluate push tokens/device identifiers and update disclosures before upload. The backend's operational logs contain route templates, status, duration and random request IDs, without request bodies, search queries or token path values; Uvicorn access logging is disabled in the Docker image. Future reverse proxies, support/email tools and crash services need their own data inventory and retention decisions. Apple's own native map service is also involved in fetching map data.

Deleting an account requires its password and an authenticated server request. The database transaction removes its account, sessions, devices, raw runs, owned territory, friendship/contest records and notifications. Identifying references in others' retained capture results are replaced with “Deleted runner”; their earned land and totals remain. A hashed receipt confirms completion without a live login. The phone retains a protected intent outside the erased account folder until server confirmation and local cleanup finish; passwords are never written to that intent. Other phones can have stale offline caches, which cannot be recalled while offline.

**Existing database dumps are not rewritten or automatically expired by deletion.** Production must implement approved backup retention and apply deletion records before exposing a restored backup. Do not publish a claim that all backup copies are instantly erased. A restored old database can currently resurrect deleted accounts if used without a reconciliation process. Raw run history currently persists until account deletion; territory expiration alone does not purge GPS records. Set an approved data lifecycle and implement it before public launch.

The privacy policy must specify the operator, contact, data/purposes, accepted-friend sharing, service providers, recording controls, retention and backups, deletion, audience and any regional requirements. Public HTTPS policy/support URLs are intentionally blank and block Release builds until configured. In-app account deletion is required for apps with account creation; merely disabling accounts is insufficient. [Apple account deletion guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/).
