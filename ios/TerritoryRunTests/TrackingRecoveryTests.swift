import XCTest
@testable import TerritoryRun

final class TrackingPolicyTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_700_000_000)
    private func fix(_ seconds: Double, accuracy: Double = 5, segment: Int = 0) -> Fix {
        Fix(latitude: 37.77, longitude: -122.42, timestamp: start.addingTimeInterval(seconds),
            accuracy: accuracy, segment: segment)
    }

    func testDelayedBackgroundBatchIsPreserved() {
        var policy = TrackingPolicy(segment: 0)
        for second in [0.0, 5, 10, 15] {
            XCTAssertEqual(policy.consider(fix(second), resumedAt: start,
                                           now: start.addingTimeInterval(120)), .accept(0))
        }
    }

    func testCachedBeforeResumeFutureAndDuplicateFixesAreIgnored() {
        var policy = TrackingPolicy(segment: 2)
        XCTAssertEqual(policy.consider(fix(0), resumedAt: start.addingTimeInterval(10), now: start), .ignore)
        XCTAssertEqual(policy.consider(fix(20), resumedAt: start, now: start), .ignore)
        XCTAssertEqual(policy.consider(fix(0), resumedAt: start, now: start), .accept(2))
        XCTAssertEqual(policy.consider(fix(0), resumedAt: start, now: start), .ignore)
    }

    func testLongGapAndPoorAccuracyNeverConnect() {
        var policy = TrackingPolicy(segment: 0)
        let now = start.addingTimeInterval(100)
        XCTAssertEqual(policy.consider(fix(0), resumedAt: start, now: now), .accept(0))
        XCTAssertEqual(policy.consider(fix(31), resumedAt: start, now: now), .accept(1))
        XCTAssertEqual(policy.consider(fix(32, accuracy: 90), resumedAt: start, now: now), .breakSegment)
        XCTAssertEqual(policy.consider(fix(33), resumedAt: start, now: now), .accept(2))
    }

    func testPauseUsesNewSegmentWithoutConnecting() {
        var policy = TrackingPolicy(last: fix(0), segment: 4)
        XCTAssertEqual(policy.consider(fix(10), resumedAt: start.addingTimeInterval(10),
                                       now: start.addingTimeInterval(10)), .accept(4))
    }
}

final class JournalRecoveryTests: XCTestCase {
    func testTornFinalAppendAndRepeatedRestartPreserveTimeAndPoints() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let journal = TrackingJournal(directory: root)
        let start = Date(timeIntervalSince1970: 1_700_000_000)
        let draft = RunDraft(clientRunId: UUID(), startedAt: start, segment: 0,
                             steps: 10, elapsedBeforeSegment: 5, resumedAt: start)
        try LocalFiles.write(draft, to: journal.metadata)
        try Data().write(to: journal.pointsURL)
        try journal.append(Fix(latitude: 37, longitude: -122, timestamp: start.addingTimeInterval(10),
                               accuracy: 5, segment: 0))
        let handle = try FileHandle(forWritingTo: journal.pointsURL)
        try handle.seekToEnd(); try handle.write(contentsOf: Data("{\"latitude\":".utf8)); try handle.close()
        let first = try XCTUnwrap(journal.recover())
        XCTAssertEqual(first.1.count, 1)
        XCTAssertEqual(first.0.elapsedBeforeSegment, 15)
        XCTAssertNil(first.0.resumedAt)
        XCTAssertEqual(first.0.clientRunId, draft.clientRunId)
        let again = try XCTUnwrap(journal.recover())
        XCTAssertEqual(again.0.elapsedBeforeSegment, 15)
        XCTAssertGreaterThan(again.0.segment, first.0.segment)
    }

    func testCorruptCompleteLineIsPreservedAndReported() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let journal = TrackingJournal(directory: root)
        try LocalFiles.write(RunDraft(clientRunId: UUID(), startedAt: Date(), segment: 0,
            steps: nil, elapsedBeforeSegment: 0, resumedAt: nil), to: journal.metadata)
        let corrupt = Data("{broken}\n".utf8)
        try corrupt.write(to: journal.pointsURL)
        XCTAssertThrowsError(try journal.recover())
        XCTAssertEqual(try Data(contentsOf: journal.pointsURL), corrupt)
    }
}

@MainActor
final class UploadRecoveryTests: XCTestCase {
    private func root() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    private func makeRun(_ id: UUID = UUID()) -> RunUpload {
        RunUpload(clientRunId: id, startedAt: Date(), endedAt: Date(), stepCount: nil, points: [])
    }

    func testOneCorruptFileDoesNotBlockOtherRuns() throws {
        let folder = try root(); defer { try? FileManager.default.removeItem(at: folder) }
        let queue = UploadQueue(); try queue.configure(directory: folder)
        try Data("broken".utf8).write(to: folder.appendingPathComponent("queue/broken.json"))
        let valid = makeRun(); try queue.enqueue(valid)
        XCTAssertEqual(queue.pending.map(\.id), [valid.id])
        XCTAssertEqual(queue.issues.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: folder.appendingPathComponent("queue/broken.json").path))
    }

    func testRetryFinishDoesNotOverwriteDurablePayload() throws {
        let folder = try root(); defer { try? FileManager.default.removeItem(at: folder) }
        let queue = UploadQueue(); try queue.configure(directory: folder)
        let original = makeRun(); try queue.enqueue(original)
        let changed = RunUpload(clientRunId: original.id, startedAt: original.startedAt,
                                endedAt: original.endedAt.addingTimeInterval(100), stepCount: 999, points: [])
        try queue.enqueue(changed)
        XCTAssertEqual(try XCTUnwrap(queue.pending.first).endedAt.timeIntervalSince1970, original.endedAt.timeIntervalSince1970, accuracy: 0.001)
        XCTAssertNil(queue.pending.first?.stepCount)
        XCTAssertTrue(try queue.hasSavedRun(original.id))
    }

    func testWrongReceiptNeverRemovesUpload() throws {
        let folder = try root(); defer { try? FileManager.default.removeItem(at: folder) }
        let queue = UploadQueue(); try queue.configure(directory: folder)
        let original = makeRun(); try queue.enqueue(original)
        let other = try Wire.decoder().decode(RunResult.self, from: Data(ContractsTests.resultJSON.utf8))
        XCTAssertThrowsError(try queue.acknowledge(original, result: other))
        XCTAssertEqual(queue.pending.map(\.id), [original.id])
    }

    func testPermanentFailurePreservesPayloadAndAllowsNextUpload() throws {
        let folder = try root(); defer { try? FileManager.default.removeItem(at: folder) }
        let queue = UploadQueue(); try queue.configure(directory: folder)
        let bad = makeRun(), good = makeRun()
        try queue.enqueue(bad); try queue.enqueue(good)
        try queue.requireAttention(bad, failure: APIError(status: 422, code: "validation_error", message: "Invalid run"))
        XCTAssertEqual(queue.pending.map(\.id), [good.id])
        XCTAssertEqual(queue.issues.count, 1)
        XCTAssertTrue(try queue.hasSavedRun(bad.id))
        let restarted = UploadQueue(); try restarted.configure(directory: folder)
        XCTAssertEqual(restarted.issues.count, 1)
        XCTAssertEqual(restarted.pending.map(\.id), [good.id])
    }
}
