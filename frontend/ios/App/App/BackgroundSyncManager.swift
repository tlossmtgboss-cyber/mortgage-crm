import UIKit
import BackgroundTasks
import os.log

// MARK: - Data Models for Background Sync / CarPlay Cache
//
// CPDashboardData, CPTaskItem, and CPRateAlert are defined in CarPlayModels.swift.
// This file only defines CarPlayContact (used exclusively by BackgroundSyncManager).

struct CarPlayContact: Codable, Identifiable {
    let id: String
    let name: String
    let phone: String?
    let email: String?
    let lastContactedAt: Date?
    let loanStage: String?
    let isHotLead: Bool

    // MARK: - Cached Date Formatters (avoid per-decode allocations)

    private static let iso8601Formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let iso8601NoFracFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    /// The /api/v1/leads/ endpoint returns a flat array of lead objects.
    /// The backend sends a combined `name` field, plus `first_name` and `last_name`.
    /// The stage field is `stage` (not `loan_stage`).
    /// `last_contacted_at` and `is_hot_lead` are not returned by the leads endpoint
    /// but are handled gracefully with defaults.
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case firstName = "first_name"
        case lastName = "last_name"
        case phone
        case email
        case lastContactedAt = "last_contacted_at"
        case loanStage = "stage"
        case isHotLead = "is_hot_lead"
        case updatedAt = "updated_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // id may come as Int or String from the backend
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = String(intId)
        } else {
            id = try c.decode(String.self, forKey: .id)
        }
        // Build display name: try combined "name" first, then "first_name" + "last_name"
        if let n = try? c.decode(String.self, forKey: .name), !n.isEmpty {
            name = n
        } else {
            let first = try? c.decode(String.self, forKey: .firstName)
            let last = try? c.decode(String.self, forKey: .lastName)
            let parts = [first, last].compactMap { $0 }.filter { !$0.isEmpty }
            name = parts.isEmpty ? "Unknown" : parts.joined(separator: " ")
        }
        phone = try c.decodeIfPresent(String.self, forKey: .phone)
        email = try c.decodeIfPresent(String.self, forKey: .email)
        // updated_at serves as a proxy for last contact time
        if let updatedStr = try? c.decode(String.self, forKey: .updatedAt) {
            lastContactedAt = CarPlayContact.iso8601Formatter.date(from: updatedStr)
                ?? CarPlayContact.iso8601NoFracFormatter.date(from: updatedStr)
        } else {
            lastContactedAt = try c.decodeIfPresent(Date.self, forKey: .lastContactedAt)
        }
        loanStage = try c.decodeIfPresent(String.self, forKey: .loanStage)
        isHotLead = try c.decodeIfPresent(Bool.self, forKey: .isHotLead) ?? false
    }

    /// Manual Encodable conformance because CodingKeys includes decode-only
    /// keys (firstName, lastName, updatedAt) that have no matching stored
    /// properties, preventing the compiler from auto-synthesizing encode(to:).
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(name, forKey: .name)
        try c.encodeIfPresent(phone, forKey: .phone)
        try c.encodeIfPresent(email, forKey: .email)
        try c.encodeIfPresent(lastContactedAt, forKey: .lastContactedAt)
        try c.encodeIfPresent(loanStage, forKey: .loanStage)
        try c.encode(isHotLead, forKey: .isHotLead)
    }
}

// MARK: - Cache Keys

// MARK: - Voice Call Summary (for Background Cache)

struct VoiceCallSummary: Codable, Identifiable {
    let id: String
    let sessionUUID: String
    let status: String
    let startedAt: Date?
    let duration: Double?
    let summary: String?
    let sentiment: String?
    let outcome: String?
    let toolCount: Int
    let messageCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case sessionUUID = "session_uuid"
        case status
        case startedAt = "started_at"
        case duration = "duration_seconds"
        case summary
        case sentiment
        case outcome
        case toolCount = "tool_count"
        case messageCount = "message_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // id may come as Int or String
        if let intId = try? c.decode(Int.self, forKey: .id) {
            id = String(intId)
        } else if let strId = try? c.decode(String.self, forKey: .id) {
            id = strId
        } else {
            // Fall back to session_uuid as id
            id = try c.decode(String.self, forKey: .sessionUUID)
        }
        sessionUUID = try c.decode(String.self, forKey: .sessionUUID)
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        startedAt = try c.decodeIfPresent(Date.self, forKey: .startedAt)
        duration = try c.decodeIfPresent(Double.self, forKey: .duration)
        summary = try c.decodeIfPresent(String.self, forKey: .summary)
        sentiment = try c.decodeIfPresent(String.self, forKey: .sentiment)
        outcome = try c.decodeIfPresent(String.self, forKey: .outcome)
        toolCount = try c.decodeIfPresent(Int.self, forKey: .toolCount) ?? 0
        messageCount = try c.decodeIfPresent(Int.self, forKey: .messageCount) ?? 0
    }
}

// MARK: - Cache Keys

private enum CacheKey {
    static let dashboard = "carplay_dashboard_cache"
    static let tasks = "carplay_tasks_cache"
    static let contacts = "carplay_contacts_cache"
    static let rateAlerts = "carplay_rate_alerts_cache"
    static let voiceCalls = "carplay_voice_calls_cache"
    static let lastSync = "carplay_last_sync"
    static let authToken = "carplay_auth_token"
}

// MARK: - BackgroundSyncManager

/// Manages background data fetching and caching for CarPlay and offline access.
///
/// This singleton coordinates:
/// - Periodic background fetch (iOS background fetch API)
/// - BGTaskScheduler-based refresh (iOS 13+ background tasks)
/// - On-demand sync when CarPlay connects
/// - Cache management for offline CarPlay access
///
/// Other agents handle AppDelegate integration (calling `performBackgroundFetch`)
/// and CarPlaySceneDelegate updates (observing `Notification.Name.carPlayDataDidUpdate`).
@available(iOS 13.0, *)
final class BackgroundSyncManager {

    static let shared = BackgroundSyncManager()

    // MARK: - Cached Date Formatters (avoid per-decode allocations)

    private static let iso8601Formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let iso8601NoFracFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static let noTZFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "BackgroundSync")
    private let bgTaskIdentifier = "com.perenniaai.crm.background-refresh"
    private let apiBaseURL: String
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    /// Decoder with convertFromSnakeCase for CPTaskItem, CPRateAlert, etc.
    private let snakeCaseDecoder: JSONDecoder
    private let syncQueue = DispatchQueue(label: "com.perenniaai.crm.sync", qos: .utility)

    /// Default minimum interval between syncs (5 minutes).
    private let defaultSyncInterval: TimeInterval = 300

    /// Minimum interval between syncs to avoid excessive API calls.
    /// Increases on 429 rate-limit responses and resets on successful syncs.
    /// Thread-safe via syncQueue, same as isSyncing.
    private var _minimumSyncInterval: TimeInterval = 300
    private var minimumSyncInterval: TimeInterval {
        get { syncQueue.sync { _minimumSyncInterval } }
        set { syncQueue.sync { _minimumSyncInterval = newValue } }
    }

    /// Whether a sync is currently in progress (atomic via syncQueue).
    private var _isSyncing = false
    private var isSyncing: Bool {
        get { syncQueue.sync { _isSyncing } }
        set { syncQueue.sync { _isSyncing = newValue } }
    }

    // MARK: - Initialization

    private init() {
        self.apiBaseURL = APIConfig.apiBaseURL

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = false
        config.allowsCellularAccess = true
        self.session = URLSession(configuration: config)

        self.encoder = JSONEncoder()
        self.encoder.dateEncodingStrategy = .iso8601

        self.decoder = JSONDecoder()
        // The backend returns ISO 8601 dates in various forms:
        //   "2026-04-13T12:00:00" (no timezone)
        //   "2026-04-13T12:00:00+00:00" (with timezone)
        //   "2026-04-13T12:00:00.123456" (with fractional seconds)
        // Use a custom strategy that tries multiple formats.
        self.decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateStr = try container.decode(String.self)

            // Try ISO8601 with fractional seconds first
            if let date = BackgroundSyncManager.iso8601Formatter.date(from: dateStr) {
                return date
            }

            // Try standard ISO8601
            if let date = BackgroundSyncManager.iso8601NoFracFormatter.date(from: dateStr) {
                return date
            }

            // Try without timezone (assume UTC)
            if let date = BackgroundSyncManager.noTZFormatter.date(from: dateStr) {
                return date
            }

            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode date: \(dateStr)")
        }

        // Snake-case decoder for models that rely on convertFromSnakeCase
        // (CPTaskItem, CPRateAlert use camelCase CodingKey case names
        // and depend on the decoder converting snake_case JSON keys).
        self.snakeCaseDecoder = JSONDecoder()
        self.snakeCaseDecoder.keyDecodingStrategy = .convertFromSnakeCase

        logger.info("BackgroundSyncManager initialized")
    }

    // MARK: - Background Task Registration

    /// Register BGTaskScheduler tasks. Call once from AppDelegate didFinishLaunchingWithOptions.
    func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: bgTaskIdentifier, using: nil) { [weak self] task in
            guard let self = self else {
                task.setTaskCompleted(success: false)
                return
            }
            guard let refreshTask = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            self.handleScheduledBackgroundTask(refreshTask)
        }
        logger.info("Registered background task: \(self.bgTaskIdentifier)")
    }

    /// Schedule the next background refresh. Call after each completed sync and on app backgrounding.
    func scheduleBackgroundRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: bgTaskIdentifier)
        // Request refresh no earlier than 15 minutes from now
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)

        do {
            try BGTaskScheduler.shared.submit(request)
            logger.info("Scheduled next background refresh")
        } catch {
            logger.error("Failed to schedule background refresh: \(error.localizedDescription)")
        }
    }

    /// Enable legacy background fetch. Call from AppDelegate didFinishLaunchingWithOptions.
    func enableLegacyBackgroundFetch(for application: UIApplication) {
        application.setMinimumBackgroundFetchInterval(UIApplication.backgroundFetchIntervalMinimum)
        logger.info("Enabled legacy background fetch with minimum interval")
    }

    // MARK: - Background Fetch (Legacy API)

    /// Perform a background fetch cycle. Called by AppDelegate's background fetch handler.
    ///
    /// - Returns: The fetch result indicating whether new data was available.
    /// Atomically check-and-set isSyncing to prevent TOCTOU races.
    /// Returns true if the caller acquired the lock, false if already syncing.
    private func acquireSyncLock() -> Bool {
        syncQueue.sync {
            if _isSyncing { return false }
            _isSyncing = true
            return true
        }
    }

    func performBackgroundFetch() async -> UIBackgroundFetchResult {
        logger.info("Starting background fetch")

        guard acquireSyncLock() else {
            logger.info("Sync already in progress, skipping")
            return .noData
        }

        guard shouldSync() else {
            isSyncing = false
            logger.info("Skipping sync, last sync was too recent")
            return .noData
        }
        defer { isSyncing = false }

        do {
            let hasNewData = try await refreshAllData()

            if hasNewData {
                logger.info("Background fetch completed with new data")
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
                scheduleBackgroundRefresh()
                return .newData
            } else {
                logger.info("Background fetch completed, no new data")
                scheduleBackgroundRefresh()
                return .noData
            }
        } catch {
            logger.error("Background fetch failed: \(error.localizedDescription)")
            scheduleBackgroundRefresh()
            return .failed
        }
    }

    // MARK: - On-Demand Sync

    /// Trigger an immediate sync, e.g. when CarPlay connects.
    /// Respects the minimum sync interval unless `force` is true.
    func syncNow(force: Bool = false) async {
        guard acquireSyncLock() else {
            logger.info("Sync already in progress, ignoring syncNow request")
            return
        }

        guard force || shouldSync() else {
            isSyncing = false
            logger.info("Recent sync exists, skipping on-demand sync")
            return
        }
        defer { isSyncing = false }

        do {
            let hasNewData = try await refreshAllData()
            if hasNewData {
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
            }
            logger.info("On-demand sync completed, newData=\(hasNewData)")
        } catch {
            logger.error("On-demand sync failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Auth Token Management

    /// Store the JWT auth token for API requests. Called from the web layer via Capacitor bridge.
    func setAuthToken(_ token: String) {
        KeychainService.shared.authToken = token
        logger.info("Auth token updated for background sync")
    }

    /// Store the refresh token for session renewal. Called alongside setAuthToken after login.
    func setRefreshToken(_ token: String) {
        KeychainService.shared.refreshToken = token
        logger.info("Refresh token updated for background sync")
    }

    /// Clear stored auth and refresh tokens on logout.
    func clearAuthToken() {
        KeychainService.shared.authToken = nil
        KeychainService.shared.refreshToken = nil
        logger.info("Auth and refresh tokens cleared")
    }

    private func getAuthToken() -> String? {
        return KeychainService.shared.authToken
    }

    private func getRefreshToken() -> String? {
        return KeychainService.shared.refreshToken
    }

    // MARK: - Cache Access (for CarPlay)

    /// Retrieve cached dashboard data for CarPlay display.
    func getCachedDashboard() -> CPDashboardData? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.dashboard,
            type: CPDashboardData.self,
            maxAge: 3600 // 1 hour
        )
    }

    /// Retrieve cached tasks for CarPlay display.
    func getCachedTasks() -> [CPTaskItem]? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.tasks,
            type: [CPTaskItem].self,
            maxAge: 3600
        )
    }

    /// Retrieve cached contacts for CarPlay display.
    func getCachedContacts() -> [CarPlayContact]? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.contacts,
            type: [CarPlayContact].self,
            maxAge: 3600
        )
    }

    /// Retrieve cached rate alerts for CarPlay display.
    func getCachedRateAlerts() -> [CPRateAlert]? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.rateAlerts,
            type: [CPRateAlert].self,
            maxAge: 3600
        )
    }

    /// Retrieve cached voice call history for offline access.
    func getCachedVoiceCalls() -> [VoiceCallSummary]? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.voiceCalls,
            type: [VoiceCallSummary].self,
            maxAge: 3600
        )
    }

    /// Timestamp of the last successful sync.
    func lastSyncTime() -> Date? {
        let interval = UserDefaults.standard.double(forKey: CacheKey.lastSync)
        guard interval > 0 else { return nil }
        return Date(timeIntervalSince1970: interval)
    }

    /// Clear all cached CarPlay data (e.g., on logout).
    func clearAllCaches() {
        syncQueue.sync {
            EncryptedCacheService.shared.delete(key: CacheKey.dashboard)
            EncryptedCacheService.shared.delete(key: CacheKey.tasks)
            EncryptedCacheService.shared.delete(key: CacheKey.contacts)
            EncryptedCacheService.shared.delete(key: CacheKey.rateAlerts)
            EncryptedCacheService.shared.delete(key: CacheKey.voiceCalls)
            UserDefaults.standard.removeObject(forKey: CacheKey.lastSync)
        }
        KeychainService.shared.authToken = nil
        KeychainService.shared.refreshToken = nil
        // Reset backoff interval
        minimumSyncInterval = defaultSyncInterval
        logger.info("All CarPlay caches cleared")
    }

    // MARK: - Partial Cache Updates (for Push Notifications)

    /// Invalidate and re-fetch only the task cache. Called when a task push notification arrives.
    func refreshTasks() async {
        do {
            let tasks = try await fetchTasks()
            cacheData(tasks: tasks)
            logger.info("Task cache refreshed from push notification, count=\(tasks.count)")
        } catch {
            logger.error("Failed to refresh task cache: \(error.localizedDescription)")
        }
    }

    /// Invalidate and re-fetch only the contacts/leads cache.
    func refreshContacts() async {
        do {
            let contacts = try await fetchContacts()
            cacheData(contacts: contacts)
            logger.info("Contact cache refreshed from push notification, count=\(contacts.count)")
        } catch {
            logger.error("Failed to refresh contact cache: \(error.localizedDescription)")
        }
    }

    /// Invalidate and re-fetch only the rate alerts cache.
    func refreshRateAlerts() async {
        do {
            let alerts = try await fetchRateAlerts()
            cacheData(rateAlerts: alerts)
            logger.info("Rate alert cache refreshed from push notification, count=\(alerts.count)")
        } catch {
            logger.error("Failed to refresh rate alert cache: \(error.localizedDescription)")
        }
    }

    /// Invalidate and re-fetch only the dashboard cache.
    func refreshDashboard() async {
        do {
            let dashboard = try await fetchDashboard()
            cacheData(dashboard: dashboard)
            logger.info("Dashboard cache refreshed")
        } catch {
            logger.error("Failed to refresh dashboard cache: \(error.localizedDescription)")
        }
    }

    /// Invalidate and re-fetch only the voice calls cache.
    func refreshVoiceCalls() async {
        do {
            let calls = try await fetchVoiceCalls()
            cacheData(voiceCalls: calls)
            logger.info("Voice calls cache refreshed, count=\(calls.count)")
        } catch {
            logger.error("Failed to refresh voice calls cache: \(error.localizedDescription)")
        }
    }

    // MARK: - Token Refresh

    /// Check if token needs refresh (within 5 min of expiry) and refresh if needed.
    /// Returns `true` if a valid token is available, `false` if the user must re-login.
    private func refreshTokenIfNeeded() async -> Bool {
        // Check session timeout (mirrors AppDelegate.enforceSessionTimeoutIfNeeded)
        let lastActiveKey = "com.perenniaai.session.lastActiveTime"
        var sessionTimeoutSeconds: TimeInterval = 900 // 15 minutes default

        // Check for MDM-managed session timeout override
        if let managedConfig = UserDefaults.standard.dictionary(forKey: "com.apple.configuration.managed"),
           let mdmTimeout = managedConfig["SessionTimeoutMinutes"] as? Int {
            sessionTimeoutSeconds = TimeInterval(mdmTimeout * 60)
        }

        if let lastActive = UserDefaults.standard.object(forKey: lastActiveKey) as? TimeInterval {
            let elapsed = Date().timeIntervalSince1970 - lastActive
            if elapsed > sessionTimeoutSeconds {
                // Session has timed out — clear token and abort sync
                KeychainService.shared.authToken = nil
                NSLog("[BackgroundSync] Session timed out (%.0fs elapsed, %.0fs limit) — clearing token", elapsed, sessionTimeoutSeconds)
                return false
            }
        }

        guard let token = KeychainService.shared.authToken else { return false }

        // Token is still fresh — no refresh needed
        if !isTokenNearExpiry(token) { return true }

        // Need a refresh token to request a new access token.
        // The /api/v1/auth/refresh endpoint expects {"refresh_token": "..."} in the body.
        guard let refreshToken = getRefreshToken() else {
            logger.warning("Access token near expiry but no refresh token available — cannot refresh")
            // If token hasn't fully expired yet, try to use it as-is
            return true
        }

        guard let url = URL(string: "\(apiBaseURL)/api/v1/auth/refresh") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("PerenniaAI-iOS/1.0 BackgroundSync", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 10

        // Send refresh token in request body as the backend expects
        let body: [String: String] = ["refresh_token": refreshToken]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return false }

            if httpResponse.statusCode == 200 || httpResponse.statusCode == 201 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let newToken = json["access_token"] as? String {
                    KeychainService.shared.authToken = newToken
                    // The /api/v1/auth/refresh endpoint rotates tokens — store the new refresh token
                    if let newRefresh = json["refresh_token"] as? String {
                        KeychainService.shared.refreshToken = newRefresh
                    }
                    logger.info("Token refreshed successfully")
                    return true
                }
            } else if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                // Refresh token is also expired — clear and require re-login
                KeychainService.shared.authToken = nil
                KeychainService.shared.refreshToken = nil
                logger.warning("Token refresh failed with \(httpResponse.statusCode) — user must re-login")
                return false
            } else if httpResponse.statusCode == 429 {
                logger.warning("Rate limited during token refresh — will retry later")
                // Don't clear tokens, just let the existing (possibly still valid) token be used
                return true
            }
        } catch {
            logger.error("Token refresh error: \(error.localizedDescription)")
        }

        // If refresh failed but token isn't fully expired yet, try to use it
        return true
    }

    /// Parse JWT payload to check if token expires within 5 minutes.
    private func isTokenNearExpiry(_ token: String) -> Bool {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return true } // malformed, treat as expired

        var base64 = String(parts[1])
        // Pad base64 to multiple of 4
        while base64.count % 4 != 0 { base64.append("=") }

        // Base64URL → Base64 standard encoding
        base64 = base64
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        guard let data = Data(base64Encoded: base64),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let exp = payload["exp"] as? TimeInterval else {
            return true // can't parse, treat as near expiry
        }

        let expiryDate = Date(timeIntervalSince1970: exp)
        let fiveMinutesFromNow = Date().addingTimeInterval(300)
        return expiryDate < fiveMinutesFromNow
    }

    // MARK: - Private: Data Fetching

    /// Refresh all data sources. Returns true if any data changed.
    private func refreshAllData() async throws -> Bool {
        // Refresh token before making any API calls
        guard await refreshTokenIfNeeded() else {
            logger.warning("No valid auth token — skipping sync")
            throw SyncError.noAuthToken
        }

        guard getAuthToken() != nil else {
            logger.warning("No auth token available, cannot sync")
            throw SyncError.noAuthToken
        }

        // Fetch all data concurrently
        async let dashboardResult = fetchDashboard()
        async let tasksResult = fetchTasks()
        async let contactsResult = fetchContacts()
        async let rateAlertsResult = fetchRateAlerts()
        async let voiceCallsResult = fetchVoiceCalls()

        // Await all results, collecting any that succeed
        var hasNewData = false

        do {
            let dashboard = try await dashboardResult
            let previousDashboard = getCachedDashboard()
            cacheData(dashboard: dashboard)
            if !dashboardEquals(previousDashboard, dashboard) {
                hasNewData = true
            }
        } catch {
            logger.error("Dashboard fetch failed: \(error.localizedDescription)")
        }

        do {
            let tasks = try await tasksResult
            let previousTasks = getCachedTasks()
            cacheData(tasks: tasks)
            if previousTasks?.count != tasks.count {
                hasNewData = true
            }
        } catch {
            logger.error("Tasks fetch failed: \(error.localizedDescription)")
        }

        do {
            let contacts = try await contactsResult
            cacheData(contacts: contacts)
            hasNewData = true  // Contacts may have changed even if count is the same
        } catch {
            logger.error("Contacts fetch failed: \(error.localizedDescription)")
        }

        do {
            let rateAlerts = try await rateAlertsResult
            let previousAlerts = getCachedRateAlerts()
            cacheData(rateAlerts: rateAlerts)
            if previousAlerts?.count != rateAlerts.count {
                hasNewData = true
            }
        } catch {
            logger.error("Rate alerts fetch failed: \(error.localizedDescription)")
        }

        do {
            let voiceCalls = try await voiceCallsResult
            let previousCalls = getCachedVoiceCalls()
            cacheData(voiceCalls: voiceCalls)
            if previousCalls?.count != voiceCalls.count {
                hasNewData = true
            }
        } catch {
            logger.error("Voice calls fetch failed: \(error.localizedDescription)")
        }

        // Sync audit logs to backend while we have connectivity
        if #available(iOS 14.0, *) {
            let auditSynced = await AuditLogger.shared.syncToBackend()
            if auditSynced > 0 {
                logger.info("Synced \(auditSynced) audit log entries to backend")
            }
        }

        // Refresh certificate pins if stale
        RemotePinManager.shared.refreshIfNeeded()

        // Update last sync timestamp
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: CacheKey.lastSync)

        // Reset backoff interval on successful sync
        if minimumSyncInterval != defaultSyncInterval {
            logger.info("Resetting sync interval from \(self.minimumSyncInterval)s back to \(self.defaultSyncInterval)s after successful sync")
            minimumSyncInterval = defaultSyncInterval
        }

        return hasNewData
    }

    private func fetchDashboard() async throws -> CPDashboardData {
        let data = try await apiRequest(path: "/api/v1/dashboard/summary")
        return try decoder.decode(CPDashboardData.self, from: data)
    }

    private func fetchTasks() async throws -> [CPTaskItem] {
        let data = try await apiRequest(path: "/api/v1/mobile/tasks", queryItems: [
            URLQueryItem(name: "status", value: "pending"),
            URLQueryItem(name: "limit", value: "20")
        ])

        // The API may return tasks in a wrapper object or as a direct array.
        // CPTaskItem uses convertFromSnakeCase (CodingKey names are camelCase).
        // Try direct array first, then wrapper.
        if let tasks = try? snakeCaseDecoder.decode([CPTaskItem].self, from: data) {
            return tasks
        }

        // Try wrapper: { "tasks": [...] }
        struct TasksWrapper: Codable {
            let tasks: [CPTaskItem]
        }
        let wrapper = try snakeCaseDecoder.decode(TasksWrapper.self, from: data)
        return wrapper.tasks
    }

    private func fetchContacts() async throws -> [CarPlayContact] {
        let data = try await apiRequest(path: "/api/v1/leads/", queryItems: [
            URLQueryItem(name: "limit", value: "20")
        ])

        // Try direct array first, then wrapper.
        if let contacts = try? decoder.decode([CarPlayContact].self, from: data) {
            return contacts
        }

        struct ContactsWrapper: Codable {
            let leads: [CarPlayContact]
        }
        let wrapper = try decoder.decode(ContactsWrapper.self, from: data)
        return wrapper.leads
    }

    private func fetchRateAlerts() async throws -> [CPRateAlert] {
        let data = try await apiRequest(path: "/api/v1/rate-alerts", queryItems: [
            URLQueryItem(name: "limit", value: "10"),
            URLQueryItem(name: "status", value: "active")
        ])

        // CPRateAlert uses convertFromSnakeCase (CodingKey names are camelCase).
        if let alerts = try? snakeCaseDecoder.decode([CPRateAlert].self, from: data) {
            return alerts
        }

        struct AlertsWrapper: Codable {
            let alerts: [CPRateAlert]
        }
        let wrapper = try snakeCaseDecoder.decode(AlertsWrapper.self, from: data)
        return wrapper.alerts
    }

    private func fetchVoiceCalls() async throws -> [VoiceCallSummary] {
        let data = try await apiRequest(path: "/api/v1/mobile-voice/calls", queryItems: [
            URLQueryItem(name: "limit", value: "20")
        ])

        // The endpoint returns { "calls": [...], "total": N }
        struct VoiceCallsWrapper: Codable {
            let calls: [VoiceCallSummary]
        }
        if let wrapper = try? decoder.decode(VoiceCallsWrapper.self, from: data) {
            return wrapper.calls
        }

        // Fall back to direct array
        return try decoder.decode([VoiceCallSummary].self, from: data)
    }

    // MARK: - Private: API Request

    private func apiRequest(path: String, queryItems: [URLQueryItem] = []) async throws -> Data {
        return try await apiRequestWithRetry(path: path, queryItems: queryItems, isRetry: false)
    }

    /// Core API request with automatic retry on 401 after token refresh.
    private func apiRequestWithRetry(path: String, queryItems: [URLQueryItem], isRetry: Bool) async throws -> Data {
        guard let token = getAuthToken() else {
            throw SyncError.noAuthToken
        }

        var components = URLComponents(string: apiBaseURL + path)
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }

        guard let url = components?.url else {
            throw SyncError.invalidURL(path)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("PerenniaAI-iOS/BackgroundSync", forHTTPHeaderField: "User-Agent")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let urlError as URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed:
                logger.info("No network connectivity for \(path)")
                throw SyncError.noNetwork
            case .timedOut:
                logger.warning("Request timed out for \(path)")
                throw SyncError.httpError(statusCode: 0)
            default:
                throw urlError
            }
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw SyncError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            return data
        case 401:
            // On first 401, try refreshing the token and retrying once
            if !isRetry {
                logger.info("Got 401 for \(path), attempting token refresh and retry")
                let refreshed = await refreshTokenIfNeeded()
                if refreshed {
                    return try await apiRequestWithRetry(path: path, queryItems: queryItems, isRetry: true)
                }
            }
            logger.warning("Auth token expired during background sync (retry=\(isRetry))")
            throw SyncError.authExpired
        case 404:
            // New endpoints may not be deployed yet — log a warning instead of error
            logger.warning("Endpoint not found (404) for \(path) — endpoint may not be deployed yet")
            throw SyncError.httpError(statusCode: 404)
        case 429:
            logger.info("Rate limited by server for \(path) — will back off")
            // Double the minimum sync interval temporarily (capped at 30 min)
            minimumSyncInterval = min(minimumSyncInterval * 2, 1800)
            throw SyncError.rateLimited
        case 500...599:
            logger.error("Server error \(httpResponse.statusCode) for \(path)")
            throw SyncError.serverError(statusCode: httpResponse.statusCode)
        default:
            logger.error("API error \(httpResponse.statusCode) for \(path)")
            throw SyncError.httpError(statusCode: httpResponse.statusCode)
        }
    }

    // MARK: - Private: Caching

    private func cacheData(dashboard: CPDashboardData? = nil,
                           tasks: [CPTaskItem]? = nil,
                           contacts: [CarPlayContact]? = nil,
                           rateAlerts: [CPRateAlert]? = nil,
                           voiceCalls: [VoiceCallSummary]? = nil) {
        if let dashboard = dashboard {
            EncryptedCacheService.shared.store(key: CacheKey.dashboard, value: dashboard)
        }
        if let tasks = tasks {
            EncryptedCacheService.shared.store(key: CacheKey.tasks, value: tasks)
        }
        if let contacts = contacts {
            EncryptedCacheService.shared.store(key: CacheKey.contacts, value: contacts)
        }
        if let rateAlerts = rateAlerts {
            EncryptedCacheService.shared.store(key: CacheKey.rateAlerts, value: rateAlerts)
        }
        if let voiceCalls = voiceCalls {
            EncryptedCacheService.shared.store(key: CacheKey.voiceCalls, value: voiceCalls)
        }
    }

    // MARK: - Private: Helpers

    private func shouldSync() -> Bool {
        let lastSync = UserDefaults.standard.double(forKey: CacheKey.lastSync)
        guard lastSync > 0 else { return true }  // Never synced before
        let elapsed = Date().timeIntervalSince1970 - lastSync
        return elapsed >= minimumSyncInterval
    }

    private func dashboardEquals(_ a: CPDashboardData?, _ b: CPDashboardData) -> Bool {
        guard let a = a else { return false }
        return a.urgentTaskCount == b.urgentTaskCount
            && a.activeLoanCount == b.activeLoanCount
            && a.rateAlertCount == b.rateAlertCount
            && a.newLeadCount == b.newLeadCount
            && a.todayAppointmentCount == b.todayAppointmentCount
    }

    private func handleScheduledBackgroundTask(_ task: BGAppRefreshTask) {
        logger.info("Handling scheduled background task")

        // Set expiration handler
        task.expirationHandler = { [weak self] in
            self?.logger.warning("Background task expired before completion")
            self?.isSyncing = false
        }

        // Run the sync
        Task {
            let result = await performBackgroundFetch()
            task.setTaskCompleted(success: result != .failed)
        }
    }
}

// MARK: - Errors

@available(iOS 13.0, *)
extension BackgroundSyncManager {
    enum SyncError: LocalizedError {
        case noAuthToken
        case invalidURL(String)
        case invalidResponse
        case authExpired
        case rateLimited
        case noNetwork
        case serverError(statusCode: Int)
        case httpError(statusCode: Int)

        var errorDescription: String? {
            switch self {
            case .noAuthToken:
                return "No authentication token available for background sync"
            case .invalidURL(let path):
                return "Invalid URL for path: \(path)"
            case .invalidResponse:
                return "Invalid HTTP response"
            case .authExpired:
                return "Authentication token has expired"
            case .rateLimited:
                return "API rate limit exceeded"
            case .noNetwork:
                return "No network connectivity"
            case .serverError(let code):
                return "Server error \(code)"
            case .httpError(let code):
                return "HTTP error \(code)"
            }
        }
    }
}
