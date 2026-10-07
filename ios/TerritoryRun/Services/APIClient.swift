import Foundation

@MainActor
final class APIClient {
    typealias CredentialsLoader = () throws -> Credentials?
    typealias CredentialsSaver = (Credentials) throws -> Void
    typealias CredentialsClearer = () throws -> Void
    private(set) var credentials: Credentials?
    private var refreshTask: Task<AuthResult, Error>?
    private var generation = 0
    let session: URLSession
    private let loadCredentials: CredentialsLoader
    private let saveCredentials: CredentialsSaver
    private let clearCredentials: CredentialsClearer
    var server: String

    init(session: URLSession = .shared,
         loadCredentials: @escaping CredentialsLoader = Keychain.load,
         saveCredentials: @escaping CredentialsSaver = Keychain.save,
         clearCredentials: @escaping CredentialsClearer = Keychain.clear) {
        self.session = session
        self.loadCredentials = loadCredentials
        self.saveCredentials = saveCredentials
        self.clearCredentials = clearCredentials
        let initialServer = Bundle.main.object(forInfoDictionaryKey: "APIBaseURL") as? String
        server = initialServer ?? ""
        #if DEBUG
        server = UserDefaults.standard.string(forKey: "serverAddress") ?? server
        #endif
    }

    func restore() throws {
        credentials = try loadCredentials()
        if let credentials { server = credentials.server }
    }

    func setServer(_ value: String) throws {
        let clean = value.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: clean), let scheme = url.scheme, let host = url.host,
              !host.isEmpty, url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, (url.path == "" || url.path == "/") else {
            throw APIError(status: 0, code: "invalid_server", message: "Enter a server address such as http://192.168.1.20:8000.")
        }
        #if DEBUG
        guard ["http", "https"].contains(scheme) else { throw invalidServer() }
        UserDefaults.standard.set(clean, forKey: "serverAddress")
        #else
        guard scheme == "https", !["localhost", "127.0.0.1", "::1"].contains(host) else { throw invalidServer() }
        #endif
        if clean != server {
            generation += 1
            refreshTask?.cancel()
            refreshTask = nil
        }
        server = clean
    }

    private func invalidServer() -> APIError {
        APIError(status: 0, code: "invalid_server", message: "This build requires a valid HTTPS server address.")
    }

    func authenticate(path: String, body: [String: String]) async throws -> Runner {
        let auth: AuthResult = try await send(path, method: "POST", body: JSONSerialization.data(withJSONObject: body), authenticated: false)
        try install(auth)
        return auth.user
    }

    func requestPasswordRecovery(email: String) async throws -> String {
        struct Acknowledgement: Decodable { let message: String }
        let result: Acknowledgement = try await send("/auth/password-recovery", method: "POST",
            body: JSONSerialization.data(withJSONObject: ["email": email.trimmingCharacters(in: .whitespacesAndNewlines)]),
            authenticated: false)
        return result.message
    }

    func reauthenticateDeletion(_ state: AccountDeletionState, password: String) async throws {
        let auth: AuthResult = try await send("/auth/login", method: "POST", body:
            JSONSerialization.data(withJSONObject: ["username": state.username, "password": password]), authenticated: false)
        guard auth.user.id == state.userId else {
            throw APIError(status: 409, code: "account_changed", message: "This login belongs to a different account. Deletion was not continued.")
        }
        try install(auth)
    }

    private func install(_ auth: AuthResult) throws {
        let value = Credentials(server: server, auth: auth)
        try saveCredentials(value)
        credentials = value
    }

    func clear() throws {
        generation += 1
        refreshTask?.cancel()
        refreshTask = nil
        try clearCredentials()
        credentials = nil
    }

    func send<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil,
                            authenticated: Bool = true) async throws -> T {
        try setServer(server)
        guard let url = URL(string: server + "/api/v1" + path) else { throw invalidServer() }
        let requestGeneration = generation
        let requestServer = server
        let originalToken = credentials?.auth.accessToken
        func request(_ token: String?) -> URLRequest {
            var req = URLRequest(url: url, timeoutInterval: path == "/runs" ? 90 : 20)
            req.httpMethod = method
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if authenticated, let token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
            return req
        }
        let (data, response) = try await session.data(for: request(originalToken))
        guard requestGeneration == generation, requestServer == server else { throw CancellationError() }
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        if http.statusCode == 401 && authenticated {
            if originalToken == credentials?.auth.accessToken { try await refresh() }
            guard requestGeneration == generation, requestServer == server else { throw CancellationError() }
            let (retryData, retryResponse) = try await session.data(for: request(credentials?.auth.accessToken))
            guard requestGeneration == generation, requestServer == server else { throw CancellationError() }
            guard let retryHTTP = retryResponse as? HTTPURLResponse else { throw URLError(.badServerResponse) }
            return try decode(retryData, status: retryHTTP.statusCode)
        }
        return try decode(data, status: http.statusCode)
    }

    private func decode<T: Decodable>(_ data: Data, status: Int) throws -> T {
        guard (200..<300).contains(status) else {
            let envelope = try? Wire.decoder().decode(APIErrorEnvelope.self, from: data)
            throw APIError(status: status, code: envelope?.error.code ?? "server_error",
                           message: envelope?.error.message ?? "The server returned an error (\(status)).")
        }
        return try Wire.decoder().decode(T.self, from: data)
    }

    private func refresh() async throws {
        if let refreshTask { _ = try await refreshTask.value; return }
        guard let token = credentials?.auth.refreshToken else {
            throw APIError(status: 401, code: "unauthorized", message: "Sign in again to sync your saved runs.")
        }
        let currentGeneration = generation
        let task = Task<AuthResult, Error> {
            let result: AuthResult = try await self.send("/auth/refresh", method: "POST",
                body: JSONSerialization.data(withJSONObject: ["refresh_token": token]), authenticated: false)
            guard currentGeneration == self.generation, !Task.isCancelled else { throw CancellationError() }
            try self.install(result)
            return result
        }
        refreshTask = task
        defer { refreshTask = nil }
        _ = try await task.value
    }
}
