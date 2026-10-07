import Foundation

struct RunDraft: Codable {
    let clientRunId: UUID
    let startedAt: Date
    var segment: Int
    var steps: Int?
    var elapsedBeforeSegment: Double
    var resumedAt: Date?
}

struct TrackingJournal {
    let directory: URL
    var metadata: URL { directory.appendingPathComponent("active.json") }
    var pointsURL: URL { directory.appendingPathComponent("active.ndjson") }

    func append(_ fix: Fix) throws {
        var data = try Wire.encoder().encode(fix)
        data.append(10)
        let handle = try FileHandle(forWritingTo: pointsURL)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
        try handle.synchronize()
    }

    func recover() throws -> (RunDraft, [Fix])? {
        guard FileManager.default.fileExists(atPath: metadata.path) else { return nil }
        var draft = try LocalFiles.read(RunDraft.self, from: metadata)
        let data = try Data(contentsOf: pointsURL)
        let complete = data.lastIndex(of: 10).map { Data(data.prefix(through: $0)) } ?? Data()
        // Never hide corruption in a complete line. Only a torn final append can be repaired.
        let points = try complete.split(separator: 10).filter { !$0.isEmpty }.map {
            try Wire.decoder().decode(Fix.self, from: Data($0))
        }
        if data.count != complete.count {
            try complete.write(to: pointsURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        }
        if let resumed = draft.resumedAt, let last = points.last {
            draft.elapsedBeforeSegment += max(0, last.timestamp.timeIntervalSince(resumed))
        }
        draft.segment = max(draft.segment, points.last?.segment ?? 0) + 1
        draft.resumedAt = nil
        try LocalFiles.write(draft, to: metadata)
        return (draft, points)
    }

    func clear() throws {
        // Metadata is the commit marker. Remove it before the journal, then in-memory state.
        for url in [metadata, pointsURL] where FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
    }
}

struct TrackingPolicy {
    enum Decision: Equatable { case ignore, breakSegment, accept(Int) }
    static let maximumGap: TimeInterval = 30
    var last: Fix?
    var segment: Int
    var needsBreak = false

    mutating func consider(_ fix: Fix, resumedAt: Date, now: Date) -> Decision {
        // Core Location may deliver a delayed batch. Validate against the recording interval,
        // not a short wall-clock age window, so valid background samples survive.
        guard fix.timestamp >= resumedAt, fix.timestamp <= now.addingTimeInterval(5),
              last.map({ fix.timestamp > $0.timestamp }) ?? true else { return .ignore }
        guard fix.latitude.isFinite, fix.longitude.isFinite,
              (-90...90).contains(fix.latitude), (-180...180).contains(fix.longitude),
              fix.accuracy.isFinite, (0...30).contains(fix.accuracy) else {
            needsBreak = true
            return .breakSegment
        }
        if let last, last.segment == segment,
           needsBreak || fix.timestamp.timeIntervalSince(last.timestamp) > Self.maximumGap {
            segment += 1
        }
        needsBreak = false
        last = Fix(latitude: fix.latitude, longitude: fix.longitude, timestamp: fix.timestamp,
                   accuracy: fix.accuracy, segment: segment)
        return .accept(segment)
    }
}
