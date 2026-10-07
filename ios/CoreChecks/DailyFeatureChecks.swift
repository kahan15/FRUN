import Foundation

@MainActor
func checkDailyFeatures(_ check: (Bool, String) throws -> Void) throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    func fix(_ x: Double, _ y: Double, segment: Int = 0, age: Double = 0, accuracy: Double = 5) -> Fix {
        Fix(latitude: 37 + y / 111_320, longitude: -122 + x / (111_320 * cos(37 * .pi / 180)),
            timestamp: now.addingTimeInterval(-age), accuracy: accuracy, segment: segment)
    }
    try check(GPSReadiness.evaluate(nil, now: now) == .waiting, "Readiness waits for a GPS sample")
    try check(GPSReadiness.evaluate(fix(0, 0), now: now) == .ready, "Fresh accurate GPS is ready")
    try check(GPSReadiness.evaluate(fix(0, 0, age: 11), now: now) == .waiting, "Stale GPS is never ready")
    try check(GPSReadiness.evaluate(fix(0, 0, accuracy: 80), now: now) == .weak, "Poor accuracy is not ready")
    let concave = [(0.0, 0.0), (160, 0), (160, 40), (40, 40), (40, 160), (0, 160), (0, 0)]
    let preview = LoopGuidance.calculate(concave.map { fix($0.0, $0.1) }, currentSegment: 0)
    try check(preview.preview.count == 6 && abs((preview.estimatedAreaM2 ?? 0) - 11200) < 1, "Concave preview preserves the cutout")
    let crossing = [fix(0, 0), fix(100, 100), fix(0, 100), fix(100, 0), fix(0, 0)]
    try check(LoopGuidance.calculate(crossing, currentSegment: 0).preview.isEmpty, "Crossing route waits for server validation")
    let gap = [fix(0, 0), fix(100, 0), fix(100, 100), fix(0, 100, segment: 1), fix(0, 0, segment: 1)]
    let afterGap = LoopGuidance.calculate(gap, currentSegment: 1)
    try check(afterGap.preview.isEmpty && abs((afterGap.distanceToStart ?? 0) - 100) < 1, "Guidance never bridges a pause")
    try check(LoopGuidance.calculate(gap, currentSegment: 2).distanceToStart == nil, "New segment waits for its own first fix")
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "America/New_York")!
    func date(_ text: String) -> Date { ISO8601DateFormatter().date(from: text)! }
    let monday = GoalRun(id: UUID(), startedAt: date("2026-10-05T04:00:00Z"), distanceM: 2000)
    let sunday = GoalRun(id: UUID(), startedAt: date("2026-10-05T03:59:00Z"), distanceM: 5000)
    let week = WeeklyProgress.calculate([sunday, monday, monday], now: date("2026-10-05T12:00:00Z"), calendar: calendar)
    try check(week.distanceM == 2000 && week.activeDays == 1, "Monday boundary and idempotent offline progress")
    try check(week.fraction(for: WeeklyGoal(kind: .distance, target: 1)) == 1, "Progress ring clamps when goal is exceeded")
    let dst = WeeklyProgress.calculate([], now: date("2026-11-01T12:00:00Z"), calendar: calendar)
    try check(dst.weekEnd.timeIntervalSince(dst.weekStart) == 169 * 3600, "Weekly boundary handles daylight saving")
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    let user = UUID()
    let first = try LocalFiles.directory(server: "https://one.test", userId: user, root: root)
    let second = try LocalFiles.directory(server: "https://two.test", userId: user, root: root)
    let goals = WeeklyGoals()
    goals.configure(directory: first)
    try goals.setGoal(WeeklyGoal(kind: .activeDays, target: 5))
    let run = RunUpload(clientRunId: UUID(), startedAt: monday.startedAt, endedAt: monday.startedAt.addingTimeInterval(100), stepCount: nil,
                        points: [fix(0, 0), fix(0, 100), fix(0, 3000, segment: 1), fix(0, 3100, segment: 1)])
    try goals.record(run); try goals.record(run)
    try check(goals.runs.count == 1 && abs(goals.runs[0].distanceM - 200) < 2, "Offline summary deduplicates and excludes gap distance")
    goals.configure(directory: second)
    try check(goals.runs.isEmpty && goals.goal == nil, "Weekly goals isolate accounts and servers")
    goals.configure(directory: first)
    try check(goals.runs.count == 1 && goals.runs[0].startedAt == monday.startedAt && goals.goal?.target == 5, "Restart preserves goal and original run date")
    try goals.setGoal(nil)
    try check(goals.goal == nil && goals.runs.count == 1, "Turning off goals preserves recorded progress")
    let damaged = second.appendingPathComponent("weekly-goals.json")
    let bytes = Data("damaged".utf8)
    try bytes.write(to: damaged)
    goals.configure(directory: second)
    var refused = false
    do { try goals.setGoal(WeeklyGoal()) } catch { refused = true }
    try check(refused && goals.issue != nil && goals.runs.isEmpty && (try Data(contentsOf: damaged)) == bytes, "Corrupt goal file is preserved without previous-account data")
}
