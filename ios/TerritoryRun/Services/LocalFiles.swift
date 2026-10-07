import Foundation
import CryptoKit
import Combine

enum LocalFiles {
    static func directory(server: String, userId: UUID, root suppliedRoot: URL? = nil) throws -> URL {
        let root = try suppliedRoot ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                              appropriateFor: nil, create: true)
        let serverKey = SHA256.hash(data: Data(server.utf8)).map { String(format: "%02x", $0) }.joined()
        let path = root.appendingPathComponent("TerritoryRun/\(serverKey)/\(userId.uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true)
        var mutable = path
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try mutable.setResourceValues(values)
        return path
    }

    static func write<T: Encodable>(_ value: T, to url: URL) throws {
        try Wire.encoder().encode(value).write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    static func read<T: Decodable>(_ type: T.Type, from url: URL) throws -> T {
        try Wire.decoder().decode(type, from: Data(contentsOf: url))
    }
}

@MainActor
final class UploadQueue: ObservableObject {
    @Published private(set) var pending: [RunUpload] = []
    @Published private(set) var issues: [String] = []
    private(set) var directory: URL?

    func configure(directory: URL) throws {
        pending = []; issues = []; self.directory = nil
        let queue = directory.appendingPathComponent("queue", isDirectory: true)
        try FileManager.default.createDirectory(at: queue, withIntermediateDirectories: true)
        self.directory = queue
        try reload()
    }

    func reload() throws {
        guard let directory else { return }
        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        var readable: [RunUpload] = []
        var failures: [String] = []
        for file in files.filter({ $0.pathExtension == "json" }).sorted(by: { $0.path < $1.path }) {
            do {
                let run = try LocalFiles.read(RunUpload.self, from: file)
                guard file.deletingPathExtension().lastPathComponent == run.id.uuidString else {
                    throw CocoaError(.fileReadCorruptFile)
                }
                readable.append(run)
            } catch { failures.append("Saved run \(file.lastPathComponent) could not be read. Its file is preserved.") }
        }
        let attention = directory.deletingLastPathComponent().appendingPathComponent("needs-attention")
        if FileManager.default.fileExists(atPath: attention.path) {
            for file in try FileManager.default.contentsOfDirectory(at: attention, includingPropertiesForKeys: nil)
                where file.pathExtension == "json" {
                failures.append("Saved run \(file.lastPathComponent) needs attention. Its upload was declined and its file is preserved.")
            }
        }
        pending = readable.sorted {
            $0.startedAt == $1.startedAt ? $0.id.uuidString < $1.id.uuidString : $0.startedAt < $1.startedAt
        }
        issues = failures
    }

    func hasSavedRun(_ id: UUID) throws -> Bool {
        guard let root = directory?.deletingLastPathComponent() else { return false }
        for name in ["queue", "receipts", "needs-attention"] {
            let file = root.appendingPathComponent("\(name)/\(id.uuidString).json")
            guard FileManager.default.fileExists(atPath: file.path) else { continue }
            let savedID = try name == "receipts"
                ? LocalFiles.read(RunResult.self, from: file).clientRunId
                : LocalFiles.read(RunUpload.self, from: file).id
            guard savedID == id else { throw CocoaError(.fileReadCorruptFile) }
            return true
        }
        return false
    }

    func enqueue(_ run: RunUpload) throws {
        guard let directory else { throw CocoaError(.fileNoSuchFile) }
        let file = directory.appendingPathComponent("\(run.id.uuidString).json")
        // Retrying Finish after a crash must not replace a committed upload with a different payload.
        if FileManager.default.fileExists(atPath: file.path) {
            let existing = try LocalFiles.read(RunUpload.self, from: file)
            guard existing.id == run.id else { throw CocoaError(.fileReadCorruptFile) }
        } else {
            try LocalFiles.write(run, to: file)
        }
        try reload()
    }

    func acknowledge(_ run: RunUpload, result: RunResult) throws {
        guard let directory else { throw CocoaError(.fileNoSuchFile) }
        guard result.clientRunId == run.id else {
            throw APIError(status: 0, code: "receipt_mismatch", message: "The server returned a receipt for a different run. Your run is still saved.")
        }
        let receipts = directory.deletingLastPathComponent().appendingPathComponent("receipts", isDirectory: true)
        try FileManager.default.createDirectory(at: receipts, withIntermediateDirectories: true)
        try LocalFiles.write(result, to: receipts.appendingPathComponent("\(run.id.uuidString).json"))
        let file = directory.appendingPathComponent("\(run.id.uuidString).json")
        if FileManager.default.fileExists(atPath: file.path) { try FileManager.default.removeItem(at: file) }
        try reload()
    }

    func requireAttention(_ run: RunUpload, failure: APIError) throws {
        guard let directory else { throw CocoaError(.fileNoSuchFile) }
        let target = directory.deletingLastPathComponent().appendingPathComponent("needs-attention", isDirectory: true)
        try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
        try LocalFiles.write(["code": failure.code, "message": failure.message],
                             to: target.appendingPathComponent("\(run.id.uuidString).error"))
        try FileManager.default.moveItem(at: directory.appendingPathComponent("\(run.id.uuidString).json"),
                                         to: target.appendingPathComponent("\(run.id.uuidString).json"))
        try reload()
    }

    func retryAttention() throws {
        guard let directory else { return }
        let held = directory.deletingLastPathComponent().appendingPathComponent("needs-attention")
        guard FileManager.default.fileExists(atPath: held.path) else { return }
        for file in try FileManager.default.contentsOfDirectory(at: held, includingPropertiesForKeys: nil)
            where file.pathExtension == "json" {
            let run = try LocalFiles.read(RunUpload.self, from: file)
            try enqueue(run)
            try FileManager.default.removeItem(at: file)
        }
        try reload()
    }

    func clearMemory() { pending = []; issues = []; directory = nil }
}
