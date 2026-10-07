import Foundation
import CoreLocation
import MapKit

enum Wire {
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            try container.encode(formatter.string(from: date))
        }
        return encoder
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: value) { return date }
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: value) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid timestamp")
        }
        return decoder
    }
}

struct Runner: Codable, Identifiable, Equatable {
    let id: UUID
    let username: String
    let displayName: String
}
struct AuthResult: Codable {
    let accessToken: String
    let refreshToken: String
    let user: Runner
}
struct Credentials: Codable {
    let server: String
    let auth: AuthResult
}
struct Fix: Codable {
    let latitude: Double
    let longitude: Double
    let timestamp: Date
    let accuracy: Double
    let segment: Int
    var coordinate: CLLocationCoordinate2D { .init(latitude: latitude, longitude: longitude) }
}
struct RunUpload: Codable, Identifiable {
    var id: UUID { clientRunId }
    let clientRunId: UUID
    let startedAt: Date
    let endedAt: Date
    let stepCount: Int?
    let points: [Fix]
}
struct Steal: Codable {
    let victimUsername: String
    let areaM2: Double
}
struct RunResult: Codable, Identifiable {
    let id: UUID
    let clientRunId: UUID
    let status: String
    let reasons: [String]
    let fragmentCount: Int
    let newAreaM2: Double
    let refreshedAreaM2: Double
    let blockedAreaM2: Double
    let stolenAreaM2: Double
    let steals: [Steal]
    let distanceM: Double
    let durationS: Double
    let wasDuplicate: Bool
    let createdAt: Date
}
struct Friend: Decodable, Identifiable {
    let id: UUID
    let username: String
    let displayName: String
    let status: String
    let incoming: Bool
}
struct Ranking: Decodable, Identifiable {
    let id: UUID
    let username: String
    let displayName: String
    let areaM2: Double
}
struct Stats: Decodable {
    let areaM2: Double
    let runCount: Int
    let distanceM: Double
    let expiringAreaM2: Double
    static let empty = Stats(areaM2: 0, runCount: 0, distanceM: 0, expiringAreaM2: 0)
}
struct FeedItem: Decodable, Identifiable {
    let id: UUID
    let kind: String
    let title: String
    let body: String
    let readAt: Date?
    let createdAt: Date
}
struct FeatureCollection: Codable {
    let type: String
    let features: [TerritoryFeature]
}
struct TerritoryFeature: Codable, Identifiable {
    let id: UUID
    let geometry: TerritoryGeometry
    let properties: TerritoryProperties
}
struct TerritoryGeometry: Codable {
    let type: String
    let coordinates: [[[[Double]]]]
    var polygons: [MKPolygon] {
        coordinates.compactMap { rings in
            guard let outer = rings.first, outer.count >= 4 else { return nil }
            func coordinates(_ ring: [[Double]]) -> [CLLocationCoordinate2D] {
                ring.filter { $0.count >= 2 }.map { .init(latitude: $0[1], longitude: $0[0]) }
            }
            let exterior = coordinates(outer)
            let holes = rings.dropFirst().map { ring -> MKPolygon in
                let points = coordinates(ring)
                return MKPolygon(coordinates: points, count: points.count)
            }
            return MKPolygon(coordinates: exterior, count: exterior.count, interiorPolygons: holes)
        }
    }
}
struct TerritoryProperties: Codable {
    let ownerId: UUID
    let username: String
    let areaM2: Double
    let claimedAt: Date
    let expiresAt: Date
    var contestedGeometry: TerritoryGeometry? = nil
}
struct OK: Decodable { let ok: Bool }
struct APIErrorEnvelope: Decodable {
    struct Detail: Decodable { let code: String; let message: String }
    let error: Detail
}
struct APIError: Error, LocalizedError {
    let status: Int
    let code: String
    let message: String
    var errorDescription: String? { message }
}
enum Display {
    static func area(_ meters: Double) -> String {
        meters >= 1_000_000 ? String(format: "%.2f km²", meters / 1_000_000) : "\(Int(meters.rounded())) m²"
    }
    static func distance(_ meters: Double) -> String { String(format: "%.2f km", meters / 1000) }
    static func duration(_ seconds: Double) -> String {
        let s = max(0, Int(seconds))
        return s >= 3600 ? String(format: "%d:%02d:%02d", s/3600, s/60%60, s%60) : String(format: "%02d:%02d", s/60, s%60)
    }
}
