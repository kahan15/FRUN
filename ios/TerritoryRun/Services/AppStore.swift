import Foundation
import Combine
import Network
import UIKit

@MainActor
final class AppStore: ObservableObject {
    let api = APIClient()
    let tracker = RunTracker()
    let queue = UploadQueue()
    let goals = WeeklyGoals()
    @Published var deletionState: AccountDeletionState?
    @Published var deletionRecoveryError: String?
    @Published var user: Runner?
    @Published var territories: [TerritoryFeature] = []
    @Published var stats = Stats.empty
    @Published var friends: [Friend] = []
    @Published var blockedRunners: [Runner] = []
    @Published var rankings: [Ranking] = []
    @Published var history: [RunResult] = []
    @Published var feed: [FeedItem] = []
    @Published var result: RunResult?
    @Published var error: String?
    @Published var syncMessage: String?
    @Published var syncing = false
    @Published private(set) var finishing = false
    @Published var connected = false
    @Published var historyHasMore = true
    private var directory: URL?
    private let monitor = NWPathMonitor()
    private var refreshInProgress = false
    private var refreshPending = false
    private var nextSyncAttempt = Date.distantPast
    private var retryAttempt = 0
    private var retryTask: Task<Void, Never>?
    private var sessionGeneration = 0

    init() {
        do { deletionState = try AccountDeletionJournal().load() }
        catch { deletionRecoveryError = "The saved deletion request could not be read. Your files are preserved. \(error.localizedDescription)" }
        do {
            try api.restore()
            if let saved = api.credentials {
                user = saved.auth.user
                if deletionState == nil && deletionRecoveryError == nil { try configureLocalFiles() }
            }
        } catch { self.error = error.localizedDescription }
        monitor.pathUpdateHandler = { [weak self] path in
            guard path.status == .satisfied else { return }
            Task { @MainActor [weak self] in await self?.sync(force: true) }
        }
        monitor.start(queue: DispatchQueue(label: "TerritoryRun.network"))
    }

    private func configureLocalFiles() throws {
        guard let user else { return }
        let folder = try LocalFiles.directory(server: api.server, userId: user.id)
        directory = folder
        try queue.configure(directory: folder)
        goals.configure(directory: folder)
        for upload in queue.pending { goals.capture(upload) }
        let journal = TrackingJournal(directory: folder)
        if FileManager.default.fileExists(atPath: journal.metadata.path) {
            let draft = try LocalFiles.read(RunDraft.self, from: journal.metadata)
            if try queue.hasSavedRun(draft.clientRunId) { try journal.clear() }
        }
        try tracker.configure(directory: folder)
        let cache = folder.appendingPathComponent("territories.json")
        if FileManager.default.fileExists(atPath: cache.path) {
            territories = try LocalFiles.read(FeatureCollection.self, from: cache).features
        }
    }

    func authenticate(register: Bool, username: String, email: String, password: String,
                      displayName: String, sex: String, server: String) async {
        guard deletionState == nil, deletionRecoveryError == nil else { return }
        do {
            try api.setServer(server)
            var body = ["username": username, "password": password]
            if register { body.merge(["email": email, "display_name": displayName, "sex": sex]) { _, new in new } }
            user = try await api.authenticate(path: register ? "/auth/register" : "/auth/login", body: body)
            sessionGeneration += 1
            nextSyncAttempt = .distantPast
            try configureLocalFiles()
            error = nil
            await sync()
        } catch { self.error = error.localizedDescription }
    }

    func refreshAll() async {
        guard deletionState == nil, deletionRecoveryError == nil, let requestedUser = user?.id else { return }
        guard !refreshInProgress else { refreshPending = true; return }
        let requestedServer = api.server
        let generation = sessionGeneration
        refreshInProgress = true
        defer {
            refreshInProgress = false
            if refreshPending {
                refreshPending = false
                Task { await self.refreshAll() }
            }
        }
        do {
            async let mapRequest: FeatureCollection = api.send("/territories")
            async let statsRequest: Stats = api.send("/territories/stats")
            async let friendsRequest: [Friend] = api.send("/friends")
            async let blocksRequest: [Runner] = api.send("/friends/blocked")
            async let ranksRequest: [Ranking] = api.send("/leaderboard")
            async let historyRequest: [RunResult] = api.send("/runs?limit=50")
            async let feedRequest: [FeedItem] = api.send("/notifications?limit=100")
            let (map, newStats, newFriends, newRanks, newHistory, newFeed, newBlocks) = try await
                (mapRequest, statsRequest, friendsRequest, ranksRequest, historyRequest, feedRequest, blocksRequest)
            guard generation == sessionGeneration, user?.id == requestedUser, api.server == requestedServer else { return }
            territories = map.features
            if let directory { try LocalFiles.write(map, to: directory.appendingPathComponent("territories.json")) }
            stats = newStats
            friends = newFriends
            blockedRunners = newBlocks
            rankings = newRanks
            history = newHistory
            historyHasMore = history.count == 50
            feed = newFeed
            connected = true
            syncMessage = queue.issues.isEmpty ? nil : queue.issues.joined(separator: "\n")
        } catch {
            guard generation == sessionGeneration, user?.id == requestedUser, api.server == requestedServer else { return }
            connected = false
            syncMessage = "Server unavailable. Saved territory remains visible; runs can still be recorded."
            handleAuth(error)
        }
    }

    func finishRun() async {
        guard deletionState == nil, tracker.active, !finishing else { return }
        finishing = true
        defer { finishing = false }
        do {
            let upload = try tracker.finish()
            try queue.enqueue(upload)
            goals.capture(upload)
            try tracker.clearAfterEnqueue()
            syncMessage = "Run saved on this phone. Waiting to sync with the server."
            finishing = false // Saving is complete; the next run need not wait for network recovery.
            await sync()
        } catch { self.error = error.localizedDescription }
    }

    func sync(force: Bool = false) async {
        guard deletionRecoveryError == nil else { return }
        if deletionState != nil { await recoverDeletion(); return }
        guard let requestedUser = user?.id, !syncing, force || Date() >= nextSyncAttempt else { return }
        let generation = sessionGeneration
        let requestedServer = api.server
        syncing = true
        // Give an in-flight upload a bounded chance to finish when the user locks the screen.
        // Disk remains the source of truth if iOS expires this execution time.
        var background = UIBackgroundTaskIdentifier.invalid
        background = UIApplication.shared.beginBackgroundTask(withName: "Save run upload") {
            if background != .invalid {
                UIApplication.shared.endBackgroundTask(background)
                background = .invalid
            }
        }
        defer {
            syncing = false
            if background != .invalid { UIApplication.shared.endBackgroundTask(background) }
        }
        do {
            for upload in queue.pending {
                do {
                    let outcome: RunResult = try await api.send("/runs", method: "POST", body: Wire.encoder().encode(upload))
                    guard generation == sessionGeneration, user?.id == requestedUser, api.server == requestedServer else { return }
                    goals.capture(upload)
                    try queue.acknowledge(upload, result: outcome)
                    result = outcome
                } catch let failure as APIError where [400, 409, 413, 422].contains(failure.status) {
                    try queue.requireAttention(upload, failure: failure)
                    // One invalid file must not starve every later run.
                }
            }
            retryAttempt = 0
            nextSyncAttempt = .distantPast
            retryTask?.cancel()
            await refreshAll()
        } catch {
            guard generation == sessionGeneration else { return }
            connected = false
            syncMessage = "\(queue.pending.count) saved run(s) waiting to sync. \(error.localizedDescription)"
            handleAuth(error)
            let delay = min(300.0, 5 * pow(2, Double(min(retryAttempt, 6))))
            retryAttempt += 1
            nextSyncAttempt = Date().addingTimeInterval(delay)
            retryTask?.cancel()
            retryTask = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(delay)) } catch { return }
                await self?.sync()
            }
        }
    }

    func retryHeldRuns() async {
        guard !syncing else { return }
        do {
            try queue.retryAttention()
            await sync(force: true)
        } catch { self.error = error.localizedDescription }
    }

    private func handleAuth(_ error: Error) {
        if let failure = error as? APIError, failure.status == 401 {
            self.error = "Your session expired. Finish any active run, then sign out and sign in to sync. Saved runs stay on this phone."
        }
    }

    func search(_ query: String) async throws -> [Runner] {
        let escaped = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed.subtracting(CharacterSet(charactersIn: "&+?#"))) ?? ""
        let generation = sessionGeneration
        let results: [Runner] = try await api.send("/friends/search?q=\(escaped)")
        guard generation == sessionGeneration else { throw CancellationError() }
        return results
    }

    func friendship(_ action: String, id: UUID) async {
        guard deletionState == nil else { return }
        let generation = sessionGeneration
        do {
            let _: OK = try await api.send("/friends/\(action)", method: "POST",
                body: JSONSerialization.data(withJSONObject: ["user_id": id.uuidString]))
            guard generation == sessionGeneration else { return }
            // Drop old friend overlays immediately after a confirmed removal, including disk cache.
            sessionGeneration += 1
            if action == "remove" || action == "block" {
                friends.removeAll { $0.id == id }
                rankings.removeAll { $0.id == id }
                territories = territories.filter { $0.properties.ownerId == user?.id }
                territories = territories.map { feature in
                    var properties = feature.properties
                    properties.contestedGeometry = nil
                    return TerritoryFeature(id: feature.id, geometry: feature.geometry, properties: properties)
                }
                if let directory {
                    try LocalFiles.write(FeatureCollection(type: "FeatureCollection", features: territories),
                                         to: directory.appendingPathComponent("territories.json"))
                }
            }
            await refreshAll()
        } catch { self.error = error.localizedDescription }
    }

    func moreHistory() async {
        guard deletionState == nil else { return }
        let generation = sessionGeneration
        do {
            let more: [RunResult] = try await api.send("/runs?limit=50&offset=\(history.count)")
            guard generation == sessionGeneration else { return }
            history.append(contentsOf: more)
            historyHasMore = more.count == 50
        } catch { self.error = error.localizedDescription }
    }

    func markRead() async {
        guard deletionState == nil else { return }
        let generation = sessionGeneration
        do {
            let _: OK = try await api.send("/notifications/read-all", method: "POST")
            let updated: [FeedItem] = try await api.send("/notifications?limit=100")
            guard generation == sessionGeneration else { return }
            feed = updated
        } catch { self.error = error.localizedDescription }
    }

    func signOut() async {
        guard deletionState == nil else { return }
        guard !tracker.active, !syncing else { error = "Finish your active run and wait for syncing to stop before signing out."; return }
        syncing = true
        sessionGeneration += 1
        retryTask?.cancel()
        defer { syncing = false }
        // Local sign-out must work even when the laptop is asleep.
        do {
            if let token = UserDefaults.standard.string(forKey: "apnsToken") {
                let _: OK = try await api.send("/devices/\(token)", method: "DELETE")
            }
            let _: OK = try await api.send("/auth/logout", method: "POST")
        } catch { syncMessage = "Signed out on this phone. The laptop session will expire automatically." }
        do {
            try api.clear()
            user = nil; territories = []; stats = .empty; history = []; feed = []; friends = []; blockedRunners = []; rankings = []
            queue.clearMemory(); goals.clearMemory(); tracker.stopGPSCheck(); directory = nil
        } catch { self.error = error.localizedDescription }
    }

    func deleteAccount(password: String) async {
        guard !syncing, deletionRecoveryError == nil else { return }
        let wasPending = deletionState != nil
        syncing = true
        defer { syncing = false }
        do {
            let journal = try AccountDeletionJournal()
            if deletionState == nil {
                guard let user else { return }
                let state = AccountDeletionState(requestId: UUID(), userId: user.id,
                    username: user.username, server: api.server)
                // Persist intent before any destructive request; never persist the password.
                try journal.save(state)
                deletionState = state
            }
            sessionGeneration += 1
            retryTask?.cancel()
            tracker.pause()
            guard let state = deletionState else { return }
            if try await deletionIsComplete(state) { try completeDeletion(state); return }
            try api.setServer(state.server)
            // Fresh password authentication also handles a session that expired while offline.
            try await api.reauthenticateDeletion(state, password: password)
            let response: AccountDeletionStatus = try await api.send("/auth/account", method: "DELETE", body:
                JSONSerialization.data(withJSONObject: ["request_id": state.requestId.uuidString, "password": password]))
            guard response.completed else { throw URLError(.badServerResponse) }
            try completeDeletion(state)
        } catch {
            // A definitive first-attempt password failure sent no deletion request.
            if !wasPending, let failure = error as? APIError, ["incorrect_password", "invalid_credentials"].contains(failure.code) {
                do { try AccountDeletionJournal().clear(); deletionState = nil }
                catch { self.error = error.localizedDescription; return }
            }
            self.error = error.localizedDescription
            syncMessage = "Deletion is not confirmed. Your saved files are preserved; reconnect and check its status."
        }
    }

    func recoverDeletion() async {
        guard !syncing, let state = deletionState else { return }
        syncing = true
        defer { syncing = false }
        do {
            if try await deletionIsComplete(state) { try completeDeletion(state) }
            else { syncMessage = "The server has not confirmed deletion. Enter your password to continue." }
        } catch { syncMessage = "Cannot confirm deletion yet. Your saved files are preserved. \(error.localizedDescription)" }
    }

    private func deletionIsComplete(_ state: AccountDeletionState) async throws -> Bool {
        if state.serverConfirmed { return true }
        try api.setServer(state.server)
        let response: AccountDeletionStatus = try await api.send("/auth/account-deletion/status", method: "POST", body:
            JSONSerialization.data(withJSONObject: ["request_id": state.requestId.uuidString]), authenticated: false)
        return response.completed
    }

    private func completeDeletion(_ state: AccountDeletionState) throws {
        let journal = try AccountDeletionJournal()
        var confirmed = state
        confirmed.serverConfirmed = true
        try journal.save(confirmed)
        deletionState = confirmed
        tracker.discardForAccountDeletion()
        try journal.eraseAccountFiles(confirmed)
        try api.clear()
        try journal.clear()
        sessionGeneration += 1
        user = nil; territories = []; stats = .empty; history = []; feed = []; friends = []; blockedRunners = []; rankings = []
        queue.clearMemory(); goals.clearMemory(); directory = nil; result = nil; connected = false
        deletionState = nil
        syncMessage = nil
        error = "Your account and this phone's saved runs have been deleted."
    }

    func registerPushToken(_ token: String) async {
        guard user != nil, deletionState == nil else { return }
        do {
            let _: OK = try await api.send("/devices", method: "POST", body: JSONSerialization.data(withJSONObject:
                ["apns_token": token, "platform": "ios", "app_version": "0.3.0"]))
        } catch { self.error = error.localizedDescription }
    }
}
