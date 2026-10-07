import Foundation

private final class CoreCheckProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, Data))!
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let (status, data) = Self.handler(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

// Executable behavior checks for shared iOS code when XCTest/Xcode is unavailable.
// XCTest suites remain the fuller development gate; these checks use the same production types.
@main
@MainActor
struct RunCoreChecks {
    static var passed = 0
    static func check(_ condition: Bool, _ description: String) throws {
        guard condition else { throw NSError(domain: "CoreChecks", code: 1,
            userInfo: [NSLocalizedDescriptionKey: description]) }
        passed += 1
    }

    static func main() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let start = Date(timeIntervalSince1970: 1_700_000_000.125)
        func fix(_ seconds: Double, accuracy: Double = 5) -> Fix {
            Fix(latitude: 37.77, longitude: -122.42, timestamp: start.addingTimeInterval(seconds), accuracy: accuracy, segment: 0)
        }
        var policy = TrackingPolicy(segment: 0)
        try check(policy.consider(fix(0), resumedAt: start, now: start.addingTimeInterval(100)) == .accept(0), "Delayed background fix")
        try check(policy.consider(fix(5), resumedAt: start, now: start.addingTimeInterval(100)) == .accept(0), "Delayed continuous batch")
        try check(policy.consider(fix(5), resumedAt: start, now: start.addingTimeInterval(100)) == .ignore, "Duplicate fix")
        try check(policy.consider(fix(40), resumedAt: start, now: start.addingTimeInterval(100)) == .accept(1), "GPS gap")
        try check(policy.consider(fix(41, accuracy: 100), resumedAt: start, now: start.addingTimeInterval(100)) == .breakSegment, "Poor accuracy break")
        try check(policy.consider(fix(42), resumedAt: start, now: start.addingTimeInterval(100)) == .accept(2), "No gap bridge")
        try check(policy.consider(fix(500), resumedAt: start, now: start) == .ignore, "Future fix")
        var resumed = TrackingPolicy(segment: 3)
        try check(resumed.consider(fix(0), resumedAt: start.addingTimeInterval(10), now: start.addingTimeInterval(10)) == .ignore, "Cached pre-resume fix")

        let id = UUID()
        let run = RunUpload(clientRunId: id, startedAt: start, endedAt: start.addingTimeInterval(10), stepCount: nil, points: [fix(0), fix(10)])
        let wire = try Wire.encoder().encode(run)
        let roundtrip = try Wire.decoder().decode(RunUpload.self, from: wire)
        try check(roundtrip.points[0].timestamp == start && roundtrip.id == id, "Wire timestamps and identity")
        let keys = try JSONSerialization.jsonObject(with: wire) as! [String: Any]
        try check(keys["client_run_id"] != nil && keys["started_at"] != nil, "Server field names")

        let queue = UploadQueue()
        try queue.configure(directory: root)
        try queue.enqueue(run)
        try queue.configure(directory: root.appendingPathComponent("other-account"))
        try check(queue.pending.isEmpty, "Account isolation")
        try queue.configure(directory: root)
        try check(queue.pending.map(\.id) == [id], "Offline restart")
        try Data("broken".utf8).write(to: root.appendingPathComponent("queue/broken.json"))
        try queue.reload()
        try check(queue.pending.count == 1 && queue.issues.count == 1, "Corrupt queue isolation")
        let changed = RunUpload(clientRunId: id, startedAt: start, endedAt: start.addingTimeInterval(500), stepCount: 100, points: [])
        try queue.enqueue(changed)
        try check(queue.pending[0].endedAt == run.endedAt && queue.pending[0].stepCount == nil, "Crash retry preserves original upload")
        func receipt(_ runID: UUID) -> RunResult {
            RunResult(id: UUID(), clientRunId: runID, status: "accepted", reasons: [], fragmentCount: 0,
                      newAreaM2: 0, refreshedAreaM2: 0, blockedAreaM2: 0, stolenAreaM2: 0, steals: [],
                      distanceM: 0, durationS: 10, wasDuplicate: false, createdAt: start)
        }
        var rejectedMismatch = false
        do { try queue.acknowledge(run, result: receipt(UUID())) } catch { rejectedMismatch = true }
        try check(rejectedMismatch && queue.pending.count == 1, "Wrong receipt retains upload")
        try queue.requireAttention(run, failure: APIError(status: 422, code: "validation_error", message: "Invalid run"))
        try check(queue.pending.isEmpty && (try queue.hasSavedRun(id)), "Declined run is retained")
        try queue.retryAttention()
        try check(queue.pending.map(\.id) == [id], "Held upload can be retried")

        let journal = TrackingJournal(directory: root)
        try LocalFiles.write(RunDraft(clientRunId: id, startedAt: start, segment: 0, steps: nil,
            elapsedBeforeSegment: 2, resumedAt: start), to: journal.metadata)
        try Data().write(to: journal.pointsURL)
        try journal.append(fix(10))
        let handle = try FileHandle(forWritingTo: journal.pointsURL)
        try handle.seekToEnd(); try handle.write(contentsOf: Data("{partial".utf8)); try handle.close()
        let recovered = try journal.recover()!
        try check(recovered.1.count == 1 && recovered.0.elapsedBeforeSegment == 12 && recovered.0.resumedAt == nil, "Torn append recovery")
        try check(try journal.recover()!.0.elapsedBeforeSegment == 12, "Restart does not double count time")
        // Crash after enqueue/ack but before active-draft cleanup: saved marker wins.
        try queue.acknowledge(run, result: receipt(id))
        try check(queue.pending.isEmpty && (try queue.hasSavedRun(id)), "Durable receipt")
        if try queue.hasSavedRun(id) { try journal.clear() }
        try check(try journal.recover() == nil, "Completed run cannot recover as active")
        let geometry = TerritoryGeometry(type: "MultiPolygon", coordinates: [[
            [[0,0],[1,0],[1,1],[0,1],[0,0]], [[0.2,0.2],[0.2,0.8],[0.8,0.8],[0.8,0.2],[0.2,0.2]]]])
        try check(geometry.polygons.count == 1 && geometry.polygons[0].interiorPolygons?.count == 1, "Native MapKit preserves holes")
        let user = Runner(id: UUID(), username: "runner", displayName: "Runner")
        var saved: Credentials? = Credentials(server: "https://laptop.example", auth:
            AuthResult(accessToken: "old", refreshToken: "old-refresh", user: user))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CoreCheckProtocol.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let newAuth = try Wire.encoder().encode(AuthResult(accessToken: "new", refreshToken: "new-refresh", user: user))
        let lock = NSLock()
        var refreshCount = 0
        CoreCheckProtocol.handler = { request in
            if request.url!.path.hasSuffix("/auth/refresh") {
                lock.lock(); refreshCount += 1; lock.unlock()
                return (200, newAuth)
            }
            return request.value(forHTTPHeaderField: "Authorization") == "Bearer new"
                ? (200, Data("{\"ok\":true}".utf8))
                : (401, Data("{\"error\":{\"code\":\"unauthorized\",\"message\":\"Expired\"}}".utf8))
        }
        let api = APIClient(session: session, loadCredentials: { saved }, saveCredentials: { saved = $0 }, clearCredentials: { saved = nil })
        try api.restore()
        async let first: OK = api.send("/first")
        async let second: OK = api.send("/second")
        let replies = try await (first, second)
        try check(replies.0.ok && replies.1.ok && refreshCount == 1, "Concurrent 401s share one refresh")
        try check(saved?.auth.refreshToken == "new-refresh", "Rotated credentials are persisted")
        let deletionRoot = root.appendingPathComponent("deletion-sandbox")
        let deletion = try AccountDeletionJournal(root: deletionRoot)
        let target = try LocalFiles.directory(server: "https://server.one", userId: user.id, root: deletionRoot)
        let otherServer = try LocalFiles.directory(server: "https://server.two", userId: user.id, root: deletionRoot)
        let otherUser = try LocalFiles.directory(server: "https://server.one", userId: UUID(), root: deletionRoot)
        try LocalFiles.write(["saved": true], to: target.appendingPathComponent("run.json"))
        var intent = AccountDeletionState(requestId: UUID(), userId: user.id, username: user.username, server: "https://server.one")
        try deletion.save(intent)
        try check(try deletion.load() == intent, "Deletion identity survives restart")
        var blockedErase = false
        do { try deletion.eraseAccountFiles(intent) } catch { blockedErase = true }
        try check(blockedErase && FileManager.default.fileExists(atPath: target.path), "Unconfirmed deletion retains local runs")
        intent.serverConfirmed = true
        try deletion.save(intent)
        try deletion.eraseAccountFiles(intent)
        try check(!FileManager.default.fileExists(atPath: target.path) && FileManager.default.fileExists(atPath: otherServer.path)
                  && FileManager.default.fileExists(atPath: otherUser.path), "Deletion isolates account and server")
        try check(try deletion.load()?.serverConfirmed == true, "Completion marker survives partial cleanup")
        try deletion.eraseAccountFiles(intent)
        try check(try deletion.load()?.requestId == intent.requestId, "Cleanup can resume after a crash")
        try deletion.clear()
        try check(try deletion.load() == nil, "Finished deletion clears intent")
        CoreCheckProtocol.handler = { _ in (200, newAuth) }
        let mismatched = AccountDeletionState(requestId: UUID(), userId: UUID(), username: user.username, server: api.server)
        var blockedAccountSwitch = false
        do { try await api.reauthenticateDeletion(mismatched, password: "test") } catch { blockedAccountSwitch = true }
        try check(blockedAccountSwitch && saved?.auth.user.id == user.id, "Reused username cannot switch deletion identity")
        try checkDailyFeatures(check)
        print("\(passed) native Swift core checks passed")
    }
}
