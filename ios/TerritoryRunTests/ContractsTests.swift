import XCTest
@testable import TerritoryRun

final class ContractsTests: XCTestCase {
    func testUploadUsesServerKeysAndPreservesTimestamps() throws {
        let date = Date(timeIntervalSince1970: 1700000000.125)
        let point = Fix(latitude: 37.77, longitude: -122.42, timestamp: date, accuracy: 5, segment: 0)
        let run = RunUpload(clientRunId: UUID(), startedAt: date, endedAt: date.addingTimeInterval(2), stepCount: 4, points: [point])
        let encoded = try Wire.encoder().encode(run)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        XCTAssertNotNil(json["client_run_id"])
        XCTAssertNotNil(json["step_count"])
        XCTAssertNil(json["clientRunId"])
        let decoded = try Wire.decoder().decode(RunUpload.self, from: encoded)
        XCTAssertEqual(decoded.points[0].timestamp.timeIntervalSince1970, date.timeIntervalSince1970, accuracy: 0.001)
        XCTAssertEqual(decoded.clientRunId, run.clientRunId)
    }

    func testResultMatchesBackendWireContract() throws {
        let data = Data(Self.resultJSON.utf8)
        let result = try Wire.decoder().decode(RunResult.self, from: data)
        XCTAssertEqual(result.newAreaM2, 10000)
        XCTAssertEqual(result.fragmentCount, 1)
        XCTAssertEqual(result.clientRunId.uuidString.lowercased(), "0f27d86b-7599-4f5b-884a-d950ad83a1ec")
        let roundtrip = try Wire.decoder().decode(RunResult.self, from: Wire.encoder().encode(result))
        XCTAssertEqual(roundtrip.id, result.id)
    }

    func testMapPreservesCarvedHoles() {
        let geometry = TerritoryGeometry(type: "MultiPolygon", coordinates: [[
            [[0,0], [1,0], [1,1], [0,1], [0,0]],
            [[0.2,0.2], [0.2,0.8], [0.8,0.8], [0.8,0.2], [0.2,0.2]]
        ]])
        XCTAssertEqual(geometry.polygons.count, 1)
        XCTAssertEqual(geometry.polygons[0].interiorPolygons?.count, 1)
    }

    static let resultJSON = """
    {"id":"1f27d86b-7599-4f5b-884a-d950ad83a1ec", "client_run_id":"0f27d86b-7599-4f5b-884a-d950ad83a1ec",
     "status":"accepted", "reasons":[], "fragment_count":1, "new_area_m2":10000.0,
     "refreshed_area_m2":0.0, "blocked_area_m2":0.0, "stolen_area_m2":0.0, "steals":[],
     "distance_m":400.0, "duration_s":200.0, "was_duplicate":false, "created_at":"2026-09-14T12:00:00.123456Z"}
    """
}

@MainActor
final class QueueTests: XCTestCase {
    func testOfflineRestartAndAcknowledgement() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let outcome = try Wire.decoder().decode(RunResult.self, from: Data(ContractsTests.resultJSON.utf8))
        let run = RunUpload(clientRunId: outcome.clientRunId, startedAt: Date(), endedAt: Date(), stepCount: nil, points: [])
        let queue = UploadQueue()
        try queue.configure(directory: root)
        try queue.enqueue(run)
        let restarted = UploadQueue()
        try restarted.configure(directory: root)
        XCTAssertEqual(restarted.pending.map(\.id), [run.id])
        try restarted.acknowledge(run, result: outcome)
        XCTAssertTrue(restarted.pending.isEmpty)
        let receipt = root.appendingPathComponent("receipts/\(run.id.uuidString).json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: receipt.path))
    }

    func testSeparateAccountsNeverSharePendingRuns() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let queue = UploadQueue()
        try queue.configure(directory: root.appendingPathComponent("runner-a"))
        try queue.enqueue(RunUpload(clientRunId: UUID(), startedAt: Date(), endedAt: Date(), stepCount: nil, points: []))
        try queue.configure(directory: root.appendingPathComponent("runner-b"))
        XCTAssertTrue(queue.pending.isEmpty)
        try queue.configure(directory: root.appendingPathComponent("runner-a"))
        XCTAssertEqual(queue.pending.count, 1)
    }
}
