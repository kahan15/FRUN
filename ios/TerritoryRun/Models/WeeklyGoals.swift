import Foundation
import Combine
import CoreLocation

enum GoalKind: String, Codable, CaseIterable {
    case distance, activeDays
    var title: String { self == .distance ? "Distance" : "Active days" }
}

struct WeeklyGoal: Codable, Equatable {
    var kind: GoalKind = .distance
    var target: Int = 10
    var valid: Bool { kind == .distance ? (1...200).contains(target) : (1...7).contains(target) }
}

struct GoalRun: Codable {
    let id: UUID
    let startedAt: Date
    let distanceM: Double

    init(_ upload: RunUpload) {
        id = upload.id
        startedAt = upload.startedAt
        // Use recorded continuous GPS only, never the straight line across a pause/gap.
        distanceM = zip(upload.points, upload.points.dropFirst()).reduce(0) { total, pair in
            guard pair.0.segment == pair.1.segment else { return total }
            return total + CLLocation(latitude: pair.0.latitude, longitude: pair.0.longitude)
                .distance(from: CLLocation(latitude: pair.1.latitude, longitude: pair.1.longitude))
        }
    }

    init(id: UUID, startedAt: Date, distanceM: Double) {
        self.id = id; self.startedAt = startedAt; self.distanceM = distanceM
    }
}

struct WeeklyProgress {
    let distanceM: Double
    let activeDays: Int
    let weekStart: Date
    let weekEnd: Date

    static func calculate(_ runs: [GoalRun], now: Date, calendar supplied: Calendar = .current) -> Self {
        var calendar = supplied
        calendar.firstWeekday = 2 // Monday, using the phone's current time zone, including DST.
        calendar.minimumDaysInFirstWeek = 4
        let interval = calendar.dateInterval(of: .weekOfYear, for: now)!
        var seen = Set<UUID>()
        var days: [Date: Double] = [:]
        for run in runs where run.startedAt >= interval.start && run.startedAt < interval.end && run.startedAt <= now {
            guard run.distanceM.isFinite, run.distanceM >= 0, seen.insert(run.id).inserted else { continue }
            days[calendar.startOfDay(for: run.startedAt), default: 0] += run.distanceM
        }
        return Self(distanceM: days.values.reduce(0, +), activeDays: days.values.filter { $0 >= 100 }.count,
                    weekStart: interval.start, weekEnd: interval.end)
    }

    func fraction(for goal: WeeklyGoal) -> Double {
        guard goal.valid else { return 0 }
        let value = goal.kind == .distance ? distanceM / 1000 : Double(activeDays)
        return min(1, max(0, value / Double(goal.target)))
    }
}

@MainActor
final class WeeklyGoals: ObservableObject {
    private struct Saved: Codable {
        var goal: WeeklyGoal?
        var runs: [GoalRun] = []
    }
    @Published private(set) var goal: WeeklyGoal?
    @Published private(set) var runs: [GoalRun] = []
    @Published private(set) var issue: String?
    private var file: URL?

    func configure(directory: URL) {
        clearMemory()
        let target = directory.appendingPathComponent("weekly-goals.json")
        do {
            if FileManager.default.fileExists(atPath: target.path) {
                let saved = try LocalFiles.read(Saved.self, from: target)
                guard saved.goal?.valid != false, saved.runs.allSatisfy({ $0.distanceM.isFinite && $0.distanceM >= 0 }) else {
                    throw CocoaError(.fileReadCorruptFile)
                }
                goal = saved.goal; runs = saved.runs
            }
            file = target
        } catch {
            // Corruption never overwrites another account's data or prevents recording.
            issue = "Weekly progress could not be read. Its file is preserved; recording still works."
        }
    }

    func setGoal(_ goal: WeeklyGoal?) throws {
        guard goal?.valid != false else { throw CocoaError(.coderInvalidValue) }
        try save(goal: goal, runs: runs)
    }

    func capture(_ run: RunUpload) {
        do { try record(run) }
        catch { issue = "Weekly progress could not be saved. Your run upload is preserved separately; progress may be incomplete." }
    }

    func record(_ run: RunUpload) throws {
        guard !runs.contains(where: { $0.id == run.id }) else { return }
        let summary = GoalRun(run)
        guard summary.distanceM.isFinite, summary.distanceM >= 0 else { throw CocoaError(.fileReadCorruptFile) }
        try save(goal: goal, runs: runs + [summary])
    }

    private func save(goal: WeeklyGoal?, runs: [GoalRun]) throws {
        guard let file else { throw CocoaError(.fileNoSuchFile) }
        try LocalFiles.write(Saved(goal: goal, runs: runs), to: file)
        self.goal = goal; self.runs = runs; issue = nil
    }

    func clearMemory() { goal = nil; runs = []; issue = nil; file = nil }
}
