import Foundation
import CoreLocation

enum GPSReadiness: Equatable {
    case waiting, weak, ready
    static func evaluate(_ fix: Fix?, now: Date) -> Self {
        guard let fix, fix.timestamp >= now.addingTimeInterval(-10), fix.timestamp <= now.addingTimeInterval(5) else { return .waiting }
        return fix.accuracy.isFinite && (0...30).contains(fix.accuracy)
            && fix.latitude.isFinite && (-90...90).contains(fix.latitude)
            && fix.longitude.isFinite && (-180...180).contains(fix.longitude) ? .ready : .weak
    }
    var title: String {
        switch self { case .waiting: return "Waiting for fresh GPS"; case .weak: return "GPS signal is weak"; case .ready: return "GPS ready" }
    }
}

struct LoopGuidance {
    var distanceToStart: Double?
    var preview: [CLLocationCoordinate2D] = []
    var estimatedAreaM2: Double?
    var detail = "A continuous loop starts with your first good GPS point."

    private struct Point {
        let x: Double
        let y: Double
        let coordinate: CLLocationCoordinate2D
    }

    static func calculate(_ fixes: [Fix], currentSegment: Int) -> Self {
        // Only the latest uninterrupted segment can guide the return to its own start.
        let segment = Array(fixes.reversed().prefix(while: { $0.segment == currentSegment }).reversed())
        guard segment.allSatisfy({ $0.latitude.isFinite && (-80...84).contains($0.latitude)
            && $0.longitude.isFinite && (-180...180).contains($0.longitude) }) else { return Self() }
        guard let first = segment.first, let last = segment.last else { return Self() }
        let distance = CLLocation(latitude: first.latitude, longitude: first.longitude)
            .distance(from: CLLocation(latitude: last.latitude, longitude: last.longitude))
        var result = Self(distanceToStart: distance)
        guard segment.count >= 3 else { return result }
        guard distance <= 30 else {
            result.detail = "Return within about 30 m of this segment's start to close the loop."
            return result
        }
        guard (-80...84).contains(first.latitude),
              segment.allSatisfy({ abs($0.longitude - first.longitude) < 180 }) else { return result }
        let scale = cos(first.latitude * .pi / 180)
        let points = segment.map { Point(x: ($0.longitude - first.longitude) * 111_320 * scale,
                                         y: ($0.latitude - first.latitude) * 111_320, coordinate: $0.coordinate) }
        guard let simplified = simplify(points), simplified.count >= 3 else {
            result.detail = "This route is complex. The server will check its enclosed loops."
            return result
        }
        var polygon = simplified
        if let end = polygon.last, hypot(end.x, end.y) < 0.25 { polygon.removeLast() }
        guard polygon.count >= 3 else { return result }
        // Never imply a self-crossing or retraced route has a simple filled capture.
        for a in polygon.indices {
            let nextA = (a + 1) % polygon.count
            for b in polygon.indices where b > a && b != nextA && (b + 1) % polygon.count != a {
                if intersects(polygon[a], polygon[nextA], polygon[b], polygon[(b + 1) % polygon.count]) {
                    result.detail = "Overlapping path: the server will check which loops qualify."
                    return result
                }
            }
        }
        let area = abs(polygon.indices.reduce(0.0) { sum, i in
            let a = polygon[i], b = polygon[(i + 1) % polygon.count]
            return sum + a.x * b.y - b.x * a.y
        }) / 2
        guard area >= 200 else {
            result.detail = "Keep going: this loop is still small or mostly a straight line."
            return result
        }
        result.preview = polygon.map(\.coordinate)
        result.estimatedAreaM2 = area
        result.detail = "Loop estimate only. GPS checks, friends and protection determine the final capture."
        return result
    }

    // Bounded four-metre simplification. Preview work cannot grow without limit on a long run.
    private static func simplify(_ points: [Point]) -> [Point]? {
        var keep: Set<Int> = [0, points.count - 1]
        var stack = [(0, points.count - 1)]
        var work = 0
        while let (start, end) = stack.popLast() {
            guard end > start + 1 else { continue }
            let a = points[start], b = points[end]
            let dx = b.x - a.x, dy = b.y - a.y, length = dx * dx + dy * dy
            var largest = 16.0, split: Int?
            for i in (start + 1)..<end {
                work += 1
                if work > 200_000 { return nil }
                let p = points[i]
                let t = length == 0 ? 0 : min(1, max(0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length))
                let distance = pow(p.x - a.x - t * dx, 2) + pow(p.y - a.y - t * dy, 2)
                if distance > largest { largest = distance; split = i }
            }
            if let split {
                keep.insert(split)
                if keep.count > 400 { return nil }
                stack.append((start, split)); stack.append((split, end))
            }
        }
        return keep.sorted().map { points[$0] }
    }

    private static func intersects(_ a: Point, _ b: Point, _ c: Point, _ d: Point) -> Bool {
        guard max(a.x, b.x) >= min(c.x, d.x), max(c.x, d.x) >= min(a.x, b.x),
              max(a.y, b.y) >= min(c.y, d.y), max(c.y, d.y) >= min(a.y, b.y) else { return false }
        func side(_ a: Point, _ b: Point, _ c: Point) -> Double { (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) }
        return side(a, b, c) * side(a, b, d) <= 0 && side(c, d, a) * side(c, d, b) <= 0
    }
}
