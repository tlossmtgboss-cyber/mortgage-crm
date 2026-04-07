/**
 * NetworkService.swift
 * Perennia AI Widget Extension — Lightweight API Client
 *
 * Reads the auth token from the shared Keychain access group and fetches
 * pipeline summary + today's tasks from the Perennia API.
 *
 * Data is cached to UserDefaults (AES-GCM encrypted via CryptoKit) so widgets
 * can render stale data when the network is unavailable or the user is logged out.
 *
 * Required integration step: The main Capacitor app must write the auth
 * token to the shared Keychain access group "group.com.perenniaai.crm"
 * with service "com.perenniaai.crm.keychain" and account "access_token".
 */

import Foundation
import CryptoKit
import Security

// MARK: - App Group Constants

enum WidgetConstants {
    static let appGroupID = "group.com.perenniaai.crm"
    static let authTokenKey = "auth_token"
    static let cachedPipelineKey = "cached_pipeline"
    static let cachedTasksKey = "cached_tasks"
    static let cachedLeadsKey = "cached_recent_leads"
    static let lastFetchKey = "last_widget_fetch"
    static let baseURL = "https://api.perenniaai.com"
    static let deepLinkScheme = "perenniaai"
}

// MARK: - Data Models

struct PipelineStage: Codable, Identifiable {
    let id: String
    let name: String
    let count: Int
    let volume: Double

    var displayName: String {
        switch id.lowercased() {
        case "application": return "Application"
        case "disclosed": return "Disclosed"
        case "processing", "in_processing": return "Processing"
        case "submitted": return "Submitted"
        case "underwriting", "in_underwriting": return "Underwriting"
        case "conditional_approval": return "Cond. Approval"
        case "ctc", "clear_to_close": return "CTC"
        case "closing": return "Closing"
        case "docs", "docs_out": return "Docs"
        case "funded", "funded_this_month": return "Funded"
        default: return name
        }
    }
}

struct PipelineSummaryData: Codable {
    let activeLoans: Int
    let closingSoon: Int
    let totalVolume: Double
    let stages: [PipelineStage]
    let tasksDueToday: Int

    enum CodingKeys: String, CodingKey {
        case activeLoans = "active_loans"
        case closingSoon = "closing_soon"
        case totalVolume = "total_volume"
        case stages
        case tasksDueToday = "tasks_due_today"
    }
}

struct WidgetTask: Codable, Identifiable {
    let id: Int
    let title: String
    let priority: String?
    let dueDate: String?
    let status: String?
    let contactName: String?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case priority
        case dueDate = "due_date"
        case status
        case contactName = "related_contact_name"
    }

    var priorityLevel: TaskPriority {
        switch (priority ?? "").lowercased() {
        case "urgent", "critical", "high":
            return .urgent
        case "normal", "medium":
            return .normal
        default:
            return .low
        }
    }

    var dueTimeString: String {
        guard let dueDate = dueDate else { return "" }
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = isoFormatter.date(from: dueDate) {
            let formatter = DateFormatter()
            formatter.dateFormat = "h:mm a"
            return formatter.string(from: date)
        }
        // Fallback: try without fractional seconds
        isoFormatter.formatOptions = [.withInternetDateTime]
        if let date = isoFormatter.date(from: dueDate) {
            let formatter = DateFormatter()
            formatter.dateFormat = "h:mm a"
            return formatter.string(from: date)
        }
        return ""
    }
}

enum TaskPriority {
    case urgent, normal, low
}

struct RecentLead: Codable {
    let name: String
    let stage: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case name
        case stage
        case createdAt = "created_at"
    }
}

struct WidgetData: Codable {
    var pipeline: PipelineSummaryData
    var tasks: [WidgetTask]
    var recentLeads: [RecentLead]
    var lastUpdated: Date
    var isAuthenticated: Bool

    static let empty = WidgetData(
        pipeline: PipelineSummaryData(
            activeLoans: 0,
            closingSoon: 0,
            totalVolume: 0,
            stages: [],
            tasksDueToday: 0
        ),
        tasks: [],
        recentLeads: [],
        lastUpdated: Date(),
        isAuthenticated: false
    )
}

// MARK: - Widget Cache Encryption

@available(iOS 14.0, *)
private struct WidgetCacheEncryption {
    private static let keychainService = "com.perenniaai.crm.widget.cache"
    private static let keychainAccount = "encryption_key"

    static func getOrCreateKey() -> SymmetricKey {
        // Try to read existing key from Keychain
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        if SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
           let data = result as? Data {
            return SymmetricKey(data: data)
        }
        // Generate and store new key
        let key = SymmetricKey(size: .bits256)
        let keyData = key.withUnsafeBytes { Data($0) }
        let addQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecValueData as String: keyData,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        SecItemAdd(addQuery as CFDictionary, nil)
        return key
    }

    static func encrypt(_ data: Data) -> Data? {
        let key = getOrCreateKey()
        guard let sealedBox = try? AES.GCM.seal(data, using: key),
              let combined = sealedBox.combined else { return nil }
        return combined
    }

    static func decrypt(_ data: Data) -> Data? {
        let key = getOrCreateKey()
        guard let sealedBox = try? AES.GCM.SealedBox(combined: data),
              let decrypted = try? AES.GCM.open(sealedBox, using: key) else { return nil }
        return decrypted
    }
}

// MARK: - Widget Network Service

final class WidgetNetworkService {

    static let shared = WidgetNetworkService()

    private let session: URLSession
    private let sharedDefaults: UserDefaults?
    private let decoder: JSONDecoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = false
        self.session = URLSession(configuration: config)
        self.sharedDefaults = UserDefaults(suiteName: WidgetConstants.appGroupID)
        self.decoder = JSONDecoder()
    }

    // MARK: - Auth Token (Keychain)

    /// Read the auth token from the shared Keychain access group.
    /// The main app writes the token here via KeychainService.
    private func getTokenFromKeychain() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.perenniaai.crm.keychain",
            kSecAttrAccount as String: "access_token",
            kSecAttrAccessGroup as String: "group.com.perenniaai.crm",
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data {
            return String(data: data, encoding: .utf8)
        }
        return nil
    }

    private var authToken: String? {
        // Primary: Shared Keychain access group
        if let token = getTokenFromKeychain(), !token.isEmpty {
            return token
        }
        return nil
    }

    var isAuthenticated: Bool {
        return authToken != nil
    }

    // MARK: - Fetch Widget Data

    func fetchWidgetData() async -> WidgetData {
        guard let token = authToken else {
            // Return cached data if available, otherwise empty with auth flag
            var cached = loadCachedData()
            cached.isAuthenticated = false
            return cached
        }

        do {
            async let dashboardResult = fetchDashboard(token: token)
            async let tasksResult = fetchTasks(token: token)

            let dashboard = try await dashboardResult
            let tasks = try await tasksResult

            let widgetData = WidgetData(
                pipeline: dashboard.pipeline,
                tasks: tasks,
                recentLeads: dashboard.recentLeads,
                lastUpdated: Date(),
                isAuthenticated: true
            )

            cacheData(widgetData)
            return widgetData

        } catch {
            // Network error: return cached data
            var cached = loadCachedData()
            cached.isAuthenticated = true
            return cached
        }
    }

    // MARK: - Dashboard Endpoint

    private struct DashboardResponse {
        let pipeline: PipelineSummaryData
        let recentLeads: [RecentLead]
    }

    private func fetchDashboard(token: String) async throws -> DashboardResponse {
        let url = URL(string: "\(WidgetConstants.baseURL)/api/v1/mobile/dashboard")!
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("PerenniaWidget/1.0", forHTTPHeaderField: "User-Agent")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WidgetError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                throw WidgetError.unauthorized
            }
            throw WidgetError.serverError(httpResponse.statusCode)
        }

        // Parse the mobile dashboard response
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw WidgetError.parseError
        }

        // Extract pipeline data
        let pipelineDict = json["pipeline"] as? [String: Any] ?? [:]
        let activeLoans = pipelineDict["active"] as? Int ?? 0
        let closingSoon = pipelineDict["closing_soon"] as? Int ?? 0
        let volume = pipelineDict["volume"] as? Double ?? 0

        let tasksDueToday = json["tasks_due_today"] as? Int ?? 0

        // Build stage breakdown from the pipeline endpoint
        let stages = await fetchPipelineStages(token: token) ?? []

        let pipeline = PipelineSummaryData(
            activeLoans: activeLoans,
            closingSoon: closingSoon,
            totalVolume: volume,
            stages: stages,
            tasksDueToday: tasksDueToday
        )

        // Extract recent leads from activity
        var recentLeads: [RecentLead] = []
        if let activity = json["recent_activity"] as? [[String: Any]] {
            for item in activity.prefix(3) {
                let summary = item["summary"] as? String ?? ""
                if !summary.isEmpty {
                    recentLeads.append(RecentLead(
                        name: summary,
                        stage: item["type"] as? String,
                        createdAt: item["time"] as? String
                    ))
                }
            }
        }

        return DashboardResponse(pipeline: pipeline, recentLeads: recentLeads)
    }

    // MARK: - Pipeline Stages

    private func fetchPipelineStages(token: String) async -> [PipelineStage]? {
        guard let url = URL(string: "\(WidgetConstants.baseURL)/api/v1/mobile/pipeline?limit=1&offset=0") else {
            return nil
        }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("PerenniaWidget/1.0", forHTTPHeaderField: "User-Agent")

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { return nil }

            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let stageCounts = json["stage_counts"] as? [String: Int] else {
                // If the pipeline endpoint doesn't return stage_counts,
                // build stages from header info
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let totalCount = json["total_count"] as? Int ?? 0
                    if totalCount > 0 {
                        return [PipelineStage(
                            id: "active",
                            name: "Active Loans",
                            count: totalCount,
                            volume: json["total_volume"] as? Double ?? 0
                        )]
                    }
                }
                return nil
            }

            return stageCounts.map { (key, value) in
                PipelineStage(id: key.lowercased(), name: key, count: value, volume: 0)
            }.sorted { $0.count > $1.count }

        } catch {
            return nil
        }
    }

    // MARK: - Tasks Endpoint

    private func fetchTasks(token: String) async throws -> [WidgetTask] {
        let url = URL(string: "\(WidgetConstants.baseURL)/api/v1/mobile/tasks?status=pending&limit=10")!
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("PerenniaWidget/1.0", forHTTPHeaderField: "User-Agent")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            return []
        }

        // The mobile tasks endpoint returns { tasks: [...], total: N }
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let tasksArray = json["tasks"] as? [[String: Any]] else {
            // Try parsing as a direct array
            if let tasks = try? decoder.decode([WidgetTask].self, from: data) {
                return tasks
            }
            return []
        }

        // Manual mapping since the shape may vary
        return tasksArray.compactMap { dict -> WidgetTask? in
            guard let id = dict["id"] as? Int,
                  let title = dict["title"] as? String else { return nil }

            return WidgetTask(
                id: id,
                title: title,
                priority: dict["priority"] as? String,
                dueDate: dict["due_date"] as? String,
                status: dict["status"] as? String,
                contactName: dict["related_contact_name"] as? String
            )
        }
    }

    // MARK: - Cache (AES-GCM encrypted)

    /// Encode data as JSON, then AES-GCM encrypt before writing to UserDefaults.
    /// Encryption key is stored in the Keychain, data at rest in UserDefaults
    /// is fully encrypted (not merely obfuscated).
    private func cacheData(_ data: WidgetData) {
        guard let defaults = sharedDefaults else { return }
        if #available(iOS 14.0, *) {
            if let jsonData = try? JSONEncoder().encode(data),
               let encrypted = WidgetCacheEncryption.encrypt(jsonData) {
                defaults.set(encrypted, forKey: "widget_cached_data")
            }
        }
        defaults.set(Date(), forKey: WidgetConstants.lastFetchKey)
    }

    /// Read AES-GCM encrypted cached data from UserDefaults and decrypt.
    private func loadCachedData() -> WidgetData {
        guard let defaults = sharedDefaults else { return .empty }

        if #available(iOS 14.0, *) {
            // Try AES-GCM encrypted format (current)
            if let encryptedData = defaults.data(forKey: "widget_cached_data"),
               let decrypted = WidgetCacheEncryption.decrypt(encryptedData),
               let cached = try? JSONDecoder().decode(WidgetData.self, from: decrypted) {
                return cached
            }

            // Fallback: read legacy base64-obfuscated format and re-encrypt
            if let obfuscated = defaults.string(forKey: "widget_cached_data"),
               let deobfuscated = Data(base64Encoded: obfuscated),
               let cached = try? JSONDecoder().decode(WidgetData.self, from: deobfuscated) {
                cacheData(cached)
                return cached
            }

            // Fallback: read raw Data format (oldest legacy)
            if let rawData = defaults.data(forKey: "widget_cached_data"),
               let cached = try? JSONDecoder().decode(WidgetData.self, from: rawData) {
                cacheData(cached)
                return cached
            }
        }

        return .empty
    }
}

// MARK: - Errors

enum WidgetError: Error, LocalizedError {
    case unauthorized
    case invalidResponse
    case serverError(Int)
    case parseError

    var errorDescription: String? {
        switch self {
        case .unauthorized:
            return "Login required"
        case .invalidResponse:
            return "Invalid server response"
        case .serverError(let code):
            return "Server error (\(code))"
        case .parseError:
            return "Could not parse response"
        }
    }
}
