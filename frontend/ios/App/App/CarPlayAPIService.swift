//
//  CarPlayAPIService.swift
//  App
//
//  Authenticated API client for CarPlay integration.
//  Reads the JWT auth token from KeychainService (secure storage), then makes
//  HTTPS requests to api.perenniaai.com.
//
//  Thread-safe singleton with 30-second response caching (in-memory + encrypted
//  persistent store) to avoid hammering the backend during CarPlay template browsing.
//

import Foundation
import os.log
import Security

// MARK: - CarPlayAPIService

/// Singleton API client for fetching live CRM data from the Perennia AI backend.
///
/// Usage:
/// ```swift
/// let dashboard = try await CarPlayAPIService.shared.fetchDashboard()
/// ```
@available(iOS 14.0, *)
final class CarPlayAPIService: @unchecked Sendable {

    // MARK: - Singleton

    static let shared = CarPlayAPIService()

    // MARK: - Constants

    /// Production API base URL (backend on Railway).
    private let baseURL = "https://api.perenniaai.com"

    /// Cache TTL in seconds. CarPlay users browse tabs rapidly so we cache
    /// responses briefly to avoid redundant network requests.
    private let cacheTTL: TimeInterval = 30.0

    // MARK: - Logging

    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "CarPlayAPI")

    // MARK: - URL Session

    /// Dedicated URLSession with sensible timeouts for automotive use.
    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = true
        // CarPlay may operate on cellular with variable latency
        config.allowsCellularAccess = true
        config.httpMaximumConnectionsPerHost = 4
        return URLSession(configuration: config)
    }()

    // MARK: - Cache

    /// Thread-safe in-memory cache keyed by request URL.
    private let cacheLock = NSLock()
    private var cache: [String: CacheEntry] = [:]

    private struct CacheEntry {
        let data: Data
        let timestamp: Date
    }

    // MARK: - JSON Decoder

    /// Shared decoder configured for the backend's snake_case JSON convention.
    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    // MARK: - Init

    private init() {
        os_log("CarPlayAPIService initialized", log: log, type: .info)
    }

    // MARK: - Public API

    /// Fetch pipeline dashboard metrics.
    /// GET /api/v1/pipeline/metrics
    func fetchDashboard() async throws -> DashboardData {
        return try await get(path: "/api/v1/pipeline/metrics")
    }

    /// Fetch pending tasks for the authenticated LO.
    /// GET /api/v1/mobile/tasks?status=pending&limit=20
    ///
    /// Uses the mobile tasks endpoint which queries the real `tasks` table
    /// and supports status filtering + overdue detection.
    func fetchTasks() async throws -> [TaskItem] {
        return try await getArray(path: "/api/v1/mobile/tasks", query: [
            "status": "pending",
            "limit": "20",
        ])
    }

    /// Fetch the most recently updated leads.
    /// GET /api/v1/leads/?limit=20&sort=-updated_at
    func fetchLeads() async throws -> [LeadItem] {
        return try await getArray(path: "/api/v1/leads/", query: [
            "limit": "20",
            "sort": "-updated_at",
        ])
    }

    /// Fetch the user's active loans.
    /// GET /api/v1/loans/?limit=20
    func fetchLoans() async throws -> [LoanItem] {
        return try await getArray(path: "/api/v1/loans/", query: [
            "limit": "20",
        ])
    }

    /// Fetch active rate monitor alerts.
    /// GET /api/v1/rate-monitor/alerts
    func fetchRateAlerts() async throws -> [RateAlert] {
        return try await getArray(path: "/api/v1/rate-monitor/alerts", query: [
            "limit": "20",
        ])
    }

    /// Fetch upcoming calendar events / appointments.
    /// GET /api/v1/scheduler/appointments?upcoming=true&limit=10
    func fetchUpcomingEvents() async throws -> [CalendarEvent] {
        return try await getArray(path: "/api/v1/scheduler/appointments", query: [
            "upcoming": "true",
            "limit": "10",
        ])
    }

    /// Mark a task as completed.
    /// PATCH /api/v1/mobile/tasks/{id} with {"status": "completed"}
    func completeTask(id: Int) async throws {
        let body: [String: Any] = ["status": "completed"]
        _ = try await patch(path: "/api/v1/mobile/tasks/\(id)", body: body)
        // Invalidate tasks cache so the next fetch reflects the change
        invalidateCache(pathPrefix: "/api/v1/mobile/tasks")
        os_log("Task %d marked as completed", log: log, type: .info, id)
    }

    /// Initiate a click-to-dial call to a lead's phone number.
    /// POST /api/v1/dialer/click-to-dial
    ///
    /// The backend uses Telnyx to place the call. The response includes a
    /// call_sid for tracking.
    func callContact(phoneNumber: String, contactName: String, leadId: Int? = nil) async throws -> CallInitiation {
        // Rate-limit call initiations to prevent accidental rapid-fire dialing
        guard RateLimiter.callInitiation.tryAcquire() else {
            os_log("Call initiation rate limited for %{public}@", log: log, type: .error, contactName)
            AuditLogger.shared.log(event: .carplayCallInitiated, details: [
                "status": "rate_limited",
                "contact_name": contactName,
                "phone_number": phoneNumber,
            ])
            throw CarPlayAPIError.rateLimited
        }

        var body: [String: Any] = [
            "phone_number": phoneNumber,
            "contact_name": contactName,
        ]
        if let leadId = leadId {
            body["lead_id"] = leadId
        }

        AuditLogger.shared.log(event: .carplayCallInitiated, details: [
            "contact_name": contactName,
            "phone_number": phoneNumber,
            "lead_id": leadId.map { String($0) } ?? "none",
        ])

        return try await post(path: "/api/v1/dialer/click-to-dial", body: body)
    }

    // MARK: - Authentication State

    /// Whether the user is currently authenticated (has a valid, non-expired token).
    var isAuthenticated: Bool {
        guard KeychainService.shared.authToken != nil else { return false }
        return !KeychainService.shared.isTokenExpired
    }

    /// Clear all cached data. Call this when the user logs out or the
    /// CarPlay scene disconnects.
    func clearCache() {
        cacheLock.lock()
        defer { cacheLock.unlock() }
        cache.removeAll()
        os_log("Cache cleared", log: log, type: .info)
    }

    // MARK: - Private: HTTP Methods

    /// Perform an authenticated GET request and decode as a single object.
    private func get<T: Codable>(path: String, query: [String: String]? = nil) async throws -> T {
        let data = try await request(method: "GET", path: path, query: query, body: nil)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            os_log("JSON decode error for %{public}@: %{public}@",
                   log: log, type: .error, path, error.localizedDescription)
            throw CarPlayAPIError.decodingFailed(path: path, underlying: error)
        }
    }

    /// Perform an authenticated GET request and decode as an array.
    /// Handles both plain arrays and paginated `{ items: [...] }` envelopes.
    private func getArray<T: Codable>(path: String, query: [String: String]? = nil) async throws -> [T] {
        let data = try await request(method: "GET", path: path, query: query, body: nil)

        // Try plain array first (most list endpoints return bare arrays)
        do {
            return try decoder.decode([T].self, from: data)
        } catch {
            // Try paginated envelope: { "items": [...], "total": N }
            do {
                let paginated = try decoder.decode(PaginatedResponse<T>.self, from: data)
                return paginated.items
            } catch {
                // Try keyed response: { "tasks": [...] } or { "alerts": [...] } etc.
                // Some endpoints wrap arrays in a named key
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    for (_, value) in json {
                        if let arrayValue = value as? [[String: Any]] {
                            let arrayData = try JSONSerialization.data(withJSONObject: arrayValue)
                            if let decoded = try? decoder.decode([T].self, from: arrayData) {
                                return decoded
                            }
                        }
                    }
                }
                os_log("JSON array decode error for %{public}@: %{public}@",
                       log: log, type: .error, path, error.localizedDescription)
                throw CarPlayAPIError.decodingFailed(path: path, underlying: error)
            }
        }
    }

    /// Perform an authenticated PATCH request.
    private func patch(path: String, body: [String: Any]) async throws -> Data {
        return try await request(method: "PATCH", path: path, query: nil, body: body, skipCache: true)
    }

    /// Perform an authenticated POST request and decode the response.
    private func post<T: Codable>(path: String, body: [String: Any]) async throws -> T {
        let data = try await request(method: "POST", path: path, query: nil, body: body, skipCache: true)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            os_log("JSON decode error for POST %{public}@: %{public}@",
                   log: log, type: .error, path, error.localizedDescription)
            throw CarPlayAPIError.decodingFailed(path: path, underlying: error)
        }
    }

    // MARK: - Private: Core Request

    /// Build, send, and validate an authenticated HTTP request.
    ///
    /// - Parameters:
    ///   - method: HTTP method (GET, POST, PATCH, etc.)
    ///   - path: API path (e.g. "/api/v1/leads/")
    ///   - query: Optional query parameters
    ///   - body: Optional JSON body (for POST/PATCH)
    ///   - skipCache: If true, always hits the network
    /// - Returns: Raw response data
    private func request(
        method: String,
        path: String,
        query: [String: String]?,
        body: [String: Any]?,
        skipCache: Bool = false
    ) async throws -> Data {

        // Client-side rate limiting to protect the backend
        guard RateLimiter.apiCall.tryAcquire(key: path) else {
            os_log("Client rate limited for %{public}@", log: log, type: .error, path)
            throw CarPlayAPIError.rateLimited
        }

        // Build URL with query parameters
        guard var components = URLComponents(string: baseURL + path) else {
            throw CarPlayAPIError.invalidURL(path: path)
        }
        if let query = query, !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components.url else {
            throw CarPlayAPIError.invalidURL(path: path)
        }

        let cacheKey = url.absoluteString

        // Check cache for GET requests
        if method == "GET" && !skipCache {
            if let cached = getCached(key: cacheKey) {
                os_log("Cache hit: %{public}@", log: log, type: .debug, path)
                return cached
            }
        }

        // Check token expiration before making network call
        if KeychainService.shared.isTokenExpired {
            os_log("Auth token is expired", log: log, type: .error)
            AuditLogger.shared.log(event: .authFailure, details: [
                "reason": "token_expired",
                "path": path,
            ])
            throw CarPlayAPIError.notAuthenticated
        }

        // Get auth token from KeychainService
        guard let token = KeychainService.shared.authToken else {
            os_log("No auth token available in KeychainService", log: log, type: .error)
            AuditLogger.shared.log(event: .authFailure, details: [
                "reason": "no_token",
                "path": path,
            ])
            throw CarPlayAPIError.notAuthenticated
        }

        // Build request
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue("PerenniaAI-CarPlay/1.0", forHTTPHeaderField: "User-Agent")

        // Attach body for POST/PATCH
        if let body = body {
            urlRequest.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        os_log("%{public}@ %{public}@", log: log, type: .info, method, path)

        // Log data access for audit trail
        AuditLogger.shared.log(event: .dataAccess, details: [
            "method": method,
            "path": path,
        ])

        // Execute request
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            os_log("Network error for %{public}@: %{public}@",
                   log: log, type: .error, path, error.localizedDescription)
            throw CarPlayAPIError.networkError(underlying: error)
        }

        // Validate HTTP status
        guard let httpResponse = response as? HTTPURLResponse else {
            throw CarPlayAPIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            // Cache successful GET responses
            if method == "GET" {
                setCache(key: cacheKey, data: data)
            }
            return data

        case 401:
            os_log("Authentication expired (401) for %{public}@", log: log, type: .error, path)
            AuditLogger.shared.log(event: .authFailure, details: [
                "reason": "401_response",
                "path": path,
            ])
            throw CarPlayAPIError.notAuthenticated

        case 403:
            os_log("Forbidden (403) for %{public}@", log: log, type: .error, path)
            AuditLogger.shared.log(event: .authFailure, details: [
                "reason": "403_forbidden",
                "path": path,
            ])
            throw CarPlayAPIError.forbidden(path: path)

        case 404:
            os_log("Not found (404) for %{public}@", log: log, type: .error, path)
            throw CarPlayAPIError.notFound(path: path)

        case 429:
            os_log("Rate limited (429) for %{public}@", log: log, type: .error, path)
            throw CarPlayAPIError.rateLimited

        case 500...599:
            // Backend production error handler replaces 500-level details with
            // "Internal server error", so we parse the body for diagnostics.
            let errorBody = String(data: data, encoding: .utf8) ?? "no body"
            os_log("Server error (%d) for %{public}@: %{public}@",
                   log: log, type: .error, httpResponse.statusCode, path, errorBody)
            throw CarPlayAPIError.serverError(statusCode: httpResponse.statusCode, body: errorBody)

        default:
            let errorBody = String(data: data, encoding: .utf8) ?? "no body"
            os_log("Unexpected status %d for %{public}@: %{public}@",
                   log: log, type: .error, httpResponse.statusCode, path, errorBody)
            throw CarPlayAPIError.httpError(statusCode: httpResponse.statusCode, body: errorBody)
        }
    }

    // MARK: - Private: Cache Operations

    /// Get cached data if it exists and is within TTL.
    private func getCached(key: String) -> Data? {
        cacheLock.lock()
        defer { cacheLock.unlock() }

        guard let entry = cache[key] else { return nil }
        if Date().timeIntervalSince(entry.timestamp) > cacheTTL {
            cache.removeValue(forKey: key)
            return nil
        }
        return entry.data
    }

    /// Store data in both the in-memory cache (fast) and the encrypted
    /// persistent store (survives process restarts).
    private func setCache(key: String, data: Data) {
        cacheLock.lock()
        defer { cacheLock.unlock() }
        cache[key] = CacheEntry(data: data, timestamp: Date())

        // Persist to encrypted store so CarPlay can recover cached data
        // after a process restart without hitting the network immediately.
        EncryptedCacheService.shared.store(key: key, value: data, shared: false)

        // Prevent unbounded growth -- evict oldest entries if cache exceeds 50 items
        if cache.count > 50 {
            let sorted = cache.sorted { $0.value.timestamp < $1.value.timestamp }
            for entry in sorted.prefix(10) {
                cache.removeValue(forKey: entry.key)
            }
        }
    }

    /// Invalidate all cache entries whose key contains the given prefix.
    private func invalidateCache(pathPrefix: String) {
        cacheLock.lock()
        defer { cacheLock.unlock() }
        let keysToRemove = cache.keys.filter { $0.contains(pathPrefix) }
        for key in keysToRemove {
            cache.removeValue(forKey: key)
        }
    }
}

// MARK: - CarPlayAPIError

/// Typed errors for CarPlay API operations.
/// Each case includes enough context for logging and spoken error messages.
enum CarPlayAPIError: LocalizedError {
    case notAuthenticated
    case invalidURL(path: String)
    case invalidResponse
    case forbidden(path: String)
    case notFound(path: String)
    case rateLimited
    case serverError(statusCode: Int, body: String)
    case httpError(statusCode: Int, body: String)
    case networkError(underlying: Error)
    case decodingFailed(path: String, underlying: Error)

    var errorDescription: String? {
        switch self {
        case .notAuthenticated:
            return "You are not signed in. Please open the Perennia AI app to sign in."
        case .invalidURL(let path):
            return "Invalid API path: \(path)"
        case .invalidResponse:
            return "Received an invalid response from the server."
        case .forbidden(let path):
            return "You don't have permission to access \(path)."
        case .notFound(let path):
            return "The requested resource was not found: \(path)"
        case .rateLimited:
            return "Too many requests. Please wait a moment and try again."
        case .serverError(let code, _):
            return "Server error (\(code)). Please try again later."
        case .httpError(let code, _):
            return "Request failed with status \(code)."
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .decodingFailed(let path, _):
            return "Failed to parse response from \(path)."
        }
    }

    /// Short spoken message suitable for CarPlay text-to-speech.
    var spokenMessage: String {
        switch self {
        case .notAuthenticated:
            return "Please sign in to the Perennia app first."
        case .networkError:
            return "Unable to connect. Check your internet connection."
        case .rateLimited:
            return "Too many requests. Try again shortly."
        case .serverError:
            return "The server is temporarily unavailable."
        default:
            return errorDescription ?? "Something went wrong."
        }
    }
}
