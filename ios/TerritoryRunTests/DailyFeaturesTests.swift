import XCTest
@testable import TerritoryRun

final class WeeklyProgressTests: XCTestCase {
    private var calendar: Calendar {
        var value = Calendar(identifier: .gregorian)
        value.timeZone = TimeZone(identifier: "America/New_York")!
        return value
    }
    private func date(_ value: String) -> Date { ISO8601DateFormatter().date(from: value)! }

    func testMondayBoundaryUsesLocalRunDateAndDeduplicatesOfflineRetry() {
        let id = UUID()
        let sunday = GoalRun(id: UUID(), startedAt: date("2026-10-05T03:59:00Z"), distanceM: 5000)
        let monday = GoalRun(id: id, startedAt: date("2026-10-05T04:00:00Z"), distanceM: 2000)
        let future = GoalRun(id: UUID(), startedAt: date("2026-10-06T12:00:00Z"), distanceM: 9000)
        let progress = WeeklyProgress.calculate([sunday, monday, monday, future], now: date("2026-10-05T12:00:00Z"), calendar: calendar)
        XCTAssertEqual(progress.distanceM, 2000)
        XCTAssertEqual(progress.activeDays, 1)
        XCTAssertEqual(progress.weekStart, monday.startedAt)
        XCTAssertEqual(progress.fraction(for: WeeklyGoal(kind: .distance, target: 1)), 1)
    }

    func testActiveDaysAggregateShortRunsWithoutRequiringAStreak() {
        let runs = [GoalRun(id: UUID(), startedAt: date("2026-10-05T12:00:00Z"), distanceM: 60),
                    GoalRun(id: UUID(), startedAt: date("2026-10-05T13:00:00Z"), distanceM: 40),
                    GoalRun(id: UUID(), startedAt: date("2026-10-07T12:00:00Z"), distanceM: 250),
                    GoalRun(id: UUID(), startedAt: date("2026-10-08T12:00:00Z"), distanceM: 0)]
        let progress = WeeklyProgress.calculate(runs, now: date("2026-10-09T12:00:00Z"), calendar: calendar)
        XCTAssertEqual(progress.distanceM, 350)
        XCTAssertEqual(progress.activeDays, 2)
        XCTAssertEqual(progress.fraction(for: WeeklyGoal(kind: .activeDays, target: 4)), 0.5)
    }

    func testDaylightSavingWeekUsesCalendarDatesNotSevenTimes24Hours() {
        let progress = WeeklyProgress.calculate([], now: date("2026-11-01T12:00:00Z"), calendar: calendar)
        XCTAssertEqual(progress.weekEnd.timeIntervalSince(progress.weekStart), 169 * 3600)
        XCTAssertEqual(progress.weekEnd, date("2026-11-02T05:00:00Z"))
    }
}

@MainActor
final class WeeklyGoalPersistenceTests: XCTestCase {
    func testOfflineRestartAccountIsolationAndRetryPreserveProgress() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let user = UUID()
        let first = try LocalFiles.directory(server: "https://one.test", userId: user, root: root)
        let second = try LocalFiles.directory(server: "https://two.test", userId: user, root: root)
        let goals = WeeklyGoals()
        goals.configure(directory: first)
        try goals.setGoal(WeeklyGoal(kind: .activeDays, target: 5))
        let started = Date(timeIntervalSince1970: 1_800_000_000)
        let run = RunUpload(clientRunId: UUID(), startedAt: started, endedAt: started.addingTimeInterval(50), stepCount: nil,
                            points: [sample(0, 0), sample(100, 0), sample(3000, 1), sample(3100, 1)])
        try goals.record(run)
        try goals.record(run)
        XCTAssertEqual(goals.runs.count, 1)
        XCTAssertEqual(goals.runs[0].distanceM, 200, accuracy: 2)
        goals.configure(directory: second)
        XCTAssertNil(goals.goal)
        XCTAssertTrue(goals.runs.isEmpty)
        goals.configure(directory: first)
        XCTAssertEqual(goals.goal, WeeklyGoal(kind: .activeDays, target: 5))
        XCTAssertEqual(goals.runs.count, 1)
        XCTAssertEqual(goals.runs[0].startedAt, run.startedAt)
        try goals.setGoal(nil)
        XCTAssertEqual(goals.runs.count, 1)
    }

    func testCorruptGoalFileIsPreservedAndCannotLeakPreviousAccount() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let file = root.appendingPathComponent("weekly-goals.json")
        let goals = WeeklyGoals()
        goals.configure(directory: root)
        try goals.setGoal(WeeklyGoal(kind: .activeDays, target: 5))
        let broken = Data("broken".utf8)
        try broken.write(to: file)
        goals.configure(directory: root)
        XCTAssertNotNil(goals.issue)
        XCTAssertNil(goals.goal)
        XCTAssertTrue(goals.runs.isEmpty)
        XCTAssertThrowsError(try goals.setGoal(WeeklyGoal()))
        XCTAssertEqual(try Data(contentsOf: file), broken)
    }

    private func sample(_ north: Double, _ segment: Int) -> Fix {
        Fix(latitude: 37 + north / 111_320, longitude: -122, timestamp: Date(), accuracy: 5, segment: segment)
    }
}

final class RunGuidanceTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private func fix(_ x: Double, _ y: Double, segment: Int = 0, age: Double = 0, accuracy: Double = 5) -> Fix {
        Fix(latitude: 37 + y / 111_320, longitude: -122 + x / (111_320 * cos(37 * .pi / 180)),
            timestamp: now.addingTimeInterval(-age), accuracy: accuracy, segment: segment)
    }

    func testReadinessRejectsStaleWeakAndFutureSamples() {
        XCTAssertEqual(GPSReadiness.evaluate(nil, now: now), .waiting)
        XCTAssertEqual(GPSReadiness.evaluate(fix(0, 0), now: now), .ready)
        XCTAssertEqual(GPSReadiness.evaluate(fix(0, 0, age: 11), now: now), .waiting)
        XCTAssertEqual(GPSReadiness.evaluate(fix(0, 0, age: -6), now: now), .waiting)
        XCTAssertEqual(GPSReadiness.evaluate(fix(0, 0, accuracy: 70), now: now), .weak)
        XCTAssertEqual(GPSReadiness.evaluate(fix(0, 0, accuracy: -1), now: now), .weak)
    }

    func testConcaveLoopPreviewKeepsTheUnvisitedCutout() throws {
        let points = [(0.0, 0.0), (160, 0), (160, 40), (40, 40), (40, 160), (0, 160), (0, 0)]
        let result = LoopGuidance.calculate(points.map { fix($0.0, $0.1) }, currentSegment: 0)
        XCTAssertEqual(result.preview.count, 6)
        XCTAssertEqual(try XCTUnwrap(result.estimatedAreaM2), 11200, accuracy: 1)
        XCTAssertEqual(try XCTUnwrap(result.distanceToStart), 0, accuracy: 1)
    }

    func testOpenAndCrossingRoutesNeverImplyAConfirmedCapture() {
        let open = [fix(0, 0), fix(100, 0), fix(100, 100)]
        XCTAssertTrue(LoopGuidance.calculate(open, currentSegment: 0).preview.isEmpty)
        let crossed = [fix(0, 0), fix(100, 100), fix(0, 100), fix(100, 0), fix(0, 0)]
        XCTAssertTrue(LoopGuidance.calculate(crossed, currentSegment: 0).preview.isEmpty)
    }

    func testPauseAndGapStartNewGuidanceWithoutBridging() throws {
        let points = [fix(0, 0), fix(100, 0), fix(100, 100), fix(0, 100, segment: 1), fix(0, 0, segment: 1)]
        let result = LoopGuidance.calculate(points, currentSegment: 1)
        XCTAssertTrue(result.preview.isEmpty)
        XCTAssertEqual(try XCTUnwrap(result.distanceToStart), 100, accuracy: 1)
        XCTAssertNil(LoopGuidance.calculate(points, currentSegment: 2).distanceToStart)
    }

    func testNearClosureIsAnEstimateAndSmallJitterStaysUnfilled() {
        let close = [fix(0, 0), fix(100, 0), fix(100, 100), fix(0, 100), fix(0, 15)]
        XCTAssertNotNil(LoopGuidance.calculate(close, currentSegment: 0).estimatedAreaM2)
        let jitter = [fix(0, 0), fix(5, 0), fix(5, 5), fix(0, 0)]
        XCTAssertTrue(LoopGuidance.calculate(jitter, currentSegment: 0).preview.isEmpty)
    }
}
