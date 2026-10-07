import Foundation

struct AccountDeletionState: Codable, Equatable {
    let requestId: UUID
    let userId: UUID
    let username: String
    let server: String
    var serverConfirmed = false
}

struct AccountDeletionStatus: Decodable { let completed: Bool }

// The intent survives lost HTTP responses, revoked sessions and partial local cleanup.
// It contains no password and lives outside the account directory being erased.
struct AccountDeletionJournal {
    let root: URL
    var file: URL { root.appendingPathComponent("TerritoryRun/account-deletion.json") }

    init(root: URL? = nil) throws {
        self.root = try root ?? FileManager.default.url(for: .applicationSupportDirectory,
            in: .userDomainMask, appropriateFor: nil, create: true)
    }

    func load() throws -> AccountDeletionState? {
        guard FileManager.default.fileExists(atPath: file.path) else { return nil }
        return try LocalFiles.read(AccountDeletionState.self, from: file)
    }

    func save(_ state: AccountDeletionState) throws {
        var parent = file.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try parent.setResourceValues(values)
        try LocalFiles.write(state, to: file)
    }

    func eraseAccountFiles(_ state: AccountDeletionState) throws {
        guard state.serverConfirmed else {
            throw APIError(status: 0, code: "deletion_unconfirmed",
                message: "Connect to the server to confirm account deletion first.")
        }
        let directory = try LocalFiles.directory(server: state.server, userId: state.userId, root: root)
        try FileManager.default.removeItem(at: directory)
    }

    func clear() throws {
        if FileManager.default.fileExists(atPath: file.path) { try FileManager.default.removeItem(at: file) }
    }
}
