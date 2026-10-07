import XCTest
@testable import TerritoryRun

private final class MockProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.handler!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@MainActor
final class APIClientTests: XCTestCase {
    func testSimultaneousUnauthorizedRequestsShareOneRefresh() async throws {
        let user = Runner(id: UUID(), username: "runner", displayName: "Runner")
        var saved: Credentials? = Credentials(server: "https://laptop.example", auth:
            AuthResult(accessToken: "old", refreshToken: "old-refresh", user: user))
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel(); MockProtocol.handler = nil }
        let lock = NSLock()
        var refreshCount = 0
        let refreshed = try Wire.encoder().encode(AuthResult(accessToken: "new", refreshToken: "new-refresh", user: user))
        MockProtocol.handler = { request in
            if request.url!.path.hasSuffix("/auth/refresh") {
                lock.lock(); refreshCount += 1; lock.unlock()
                return (200, refreshed)
            }
            if request.value(forHTTPHeaderField: "Authorization") == "Bearer new" {
                return (200, Data("{\"ok\":true}".utf8))
            }
            return (401, Data("{\"error\":{\"code\":\"unauthorized\",\"message\":\"Expired\"}}".utf8))
        }
        let api = APIClient(session: session, loadCredentials: { saved }, saveCredentials: { saved = $0 }, clearCredentials: { saved = nil })
        try api.restore()
        async let first: OK = api.send("/first")
        async let second: OK = api.send("/second")
        let results = try await (first, second)
        XCTAssertTrue(results.0.ok && results.1.ok)
        XCTAssertEqual(refreshCount, 1)
        XCTAssertEqual(saved?.auth.refreshToken, "new-refresh")
    }
    func testRecoveryDoesNotSendCredentialsOrReplaceSavedSession() async throws {
        let user = Runner(id: UUID(), username: "runner", displayName: "Runner")
        let saved = Credentials(server: "https://laptop.example", auth:
            AuthResult(accessToken: "private-access", refreshToken: "private-refresh", user: user))
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel(); MockProtocol.handler = nil }
        var writes = 0
        MockProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/auth/password-recovery")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
            return (202, Data("{\"message\":\"If an eligible account uses that email, a recovery link will be sent.\"}".utf8))
        }
        let api = APIClient(session: session, loadCredentials: { saved }, saveCredentials: { _ in writes += 1 }, clearCredentials: { writes += 1 })
        try api.restore()
        let response = try await api.requestPasswordRecovery(email: "synthetic@example.com")
        XCTAssertTrue(response.contains("eligible account"))
        XCTAssertEqual(api.credentials?.auth.accessToken, "private-access")
        XCTAssertEqual(writes, 0)
    }

    func testUnavailableRecoveryShowsServerErrorWithoutRefreshingSession() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel(); MockProtocol.handler = nil }
        var calls = 0
        MockProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.url?.path, "/api/v1/auth/password-recovery")
            return (503, Data("{\"error\":{\"code\":\"recovery_unavailable\",\"message\":\"Password recovery is not available yet.\"}}".utf8))
        }
        let api = APIClient(session: session, loadCredentials: { nil }, saveCredentials: { _ in XCTFail("Must not save credentials") }, clearCredentials: {})
        api.server = "https://laptop.example"
        do {
            _ = try await api.requestPasswordRecovery(email: "synthetic@example.com")
            XCTFail("Expected unavailable recovery")
        } catch let error as APIError {
            XCTAssertEqual(error.status, 503)
            XCTAssertEqual(error.code, "recovery_unavailable")
        }
        XCTAssertEqual(calls, 1)
    }
}
