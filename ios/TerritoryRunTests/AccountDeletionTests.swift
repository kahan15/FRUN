import XCTest
@testable import TerritoryRun

final class AccountDeletionTests: XCTestCase {
    func testRestartAndScopedCleanupRequireServerConfirmation() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let journal = try AccountDeletionJournal(root: root)
        var state = AccountDeletionState(requestId: UUID(), userId: UUID(), username: "runner", server: "https://one.test")
        let own = try LocalFiles.directory(server: state.server, userId: state.userId, root: root)
        let other = try LocalFiles.directory(server: "https://two.test", userId: state.userId, root: root)
        try LocalFiles.write(["saved": true], to: own.appendingPathComponent("run.json"))
        try journal.save(state)
        XCTAssertEqual(try journal.load(), state)
        XCTAssertThrowsError(try journal.eraseAccountFiles(state))
        XCTAssertTrue(FileManager.default.fileExists(atPath: own.path))
        state.serverConfirmed = true
        try journal.save(state)
        try journal.eraseAccountFiles(state)
        XCTAssertFalse(FileManager.default.fileExists(atPath: own.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: other.path))
        XCTAssertEqual(try journal.load(), state)
        try journal.eraseAccountFiles(state)
        try journal.clear()
        XCTAssertNil(try journal.load())
    }

    func testCorruptIntentFailsClosed() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let journal = try AccountDeletionJournal(root: root)
        try journal.save(AccountDeletionState(requestId: UUID(), userId: UUID(), username: "runner", server: "https://one.test"))
        try Data("broken".utf8).write(to: journal.file)
        XCTAssertThrowsError(try journal.load())
        XCTAssertTrue(FileManager.default.fileExists(atPath: journal.file.path))
    }
}
