import UIKit
import BackgroundTasks
import os.log

// MARK: - Data Models for CarPlay Cache

/// Dashboard summary data cached for CarPlay display.
struct DashboardData: Codable {
    let urgentTaskCount: Int
    let activeLoanCount: Int
    let rateAlertCount: Int
    let newLeadCount: Int
    let todayAppointmentCount: Int
    let pipelineSummary: PipelineSummary?

    struct PipelineSummary: Codable {
        let applicationCount: Int
        let processingCount: Int
        let underwritingCount: Int
        let clearToCloseCount: Int
    }
}

/// A single task item for CarPlay task lists.
struct TaskItem: Codable, Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let dueDate: Date?
    let priority: TaskPriority
    let isOverdue: Bool
    let relatedContactName: String?
    let relatedContactPhone: String?

    enum TaskPriority: String, Codable {
        case urgent
        case high
        case normal
        case low
    }
}

/// A contact/lead for CarPlay contact lists.
struct CarPlayContact: Codable, Identifiable {
    let id: String
    let name: String
    let phone: String?
    let email: String?
    let lastContactedAt: Date?
    let loanStage: String?
    let isHotLead: Bool
}

/// A rate alert for CarPlay display.
struct RateAlert: Codable, Identifiable {
    let id: String
    let productName: String
    let currentRate: Double
    let previousRate: Double
    let changeDirection: String  // "up" or "down"
    let timestamp: Date
}

// MARK: - Cache Keys

private enum CacheKey {
    static let dashboard = "carplay_dashboard_cache"
    static let tasks = "carplay_tasks_cache"
    static let contacts = "carplay_contacts_cache"
    static let rateAlerts = "carplay_rate_alerts_cache"
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

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "BackgroundSync")
    private let bgTaskIdentifier = "com.perenniaai.crm.background-refresh"
    private let apiBaseURL: String
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let syncQueue = DispatchQueue(label: "com.perenniaai.crm.sync", qos: .utility)

    /// Minimum interval between syncs to avoid excessive API calls (5 minutes).
    private let minimumSyncInterval: TimeInterval = 300

    /// Whether a sync is currently in progress (atomic via syncQueue).
    private var _isSyncing = false
    private var isSyncing: Bool {
        get { syncQueue.sync { _isSyncing } }
        set { syncQueue.sync { _isSyncing = newValue } }
    }

    // MARK: - Initialization

    private init() {
        self.apiBaseURL = "https://api.perenniaai.com"

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = false
        config.allowsCellularAccess = true
        self.session = URLSession(configuration: config)

        self.encoder = JSONEncoder()
        self.encoder.dateEncodingStrategy = .iso8601

        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601

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
            self.handleScheduledBackgroundTask(task as! BGAppRefreshTask)
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
    func performBackgroundFetch() async -> UIBackgroundFetchResult {
        logger.info("Starting background fetch")

        guard !isSyncing else {
            logger.info("Sync already in progress, skipping")
            return .noData
        }

        guard shouldSync() else {
            logger.info("Skipping sync, last sync was too recent")
            return .noData
        }

        isSyncing = true
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
        guard !isSyncing else {
            logger.info("Sync already in progress, ignoring syncNow request")
            return
        }

        guard force || shouldSync() else {
            logger.info("Recent sync exists, skipping on-demand sync")
            return
        }

        isSyncing = true
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

    /// Clear stored auth token on logout.
    func clearAuthToken() {
        KeychainService.shared.authToken = nil
        logger.info("Auth token cleared")
    }

    private func getAuthToken() -> String? {
        return KeychainService.shared.authToken
    }

    // MARK: - Cache Access (for CarPlay)

    /// Retrieve cached dashboard data for CarPlay display.
    func getCachedDashboard() -> DashboardData? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.dashboard,
            type: DashboardData.self,
            maxAge: 3600 // 1 hour
        )
    }

    /// Retrieve cached tasks for CarPlay display.
    func getCachedTasks() -> [TaskItem]? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.tasks,
            type: [TaskItem].self,
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
    func getCachedRateAlerts() -> [RateAlert]? {
        return EncryptedCacheService.shared.retrieve(
            key: CacheKey.rateAlerts,
            type: [RateAlert].self,
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
            UserDefaults.standard.removeObject(forKey: CacheKey.lastSync)
        }
        KeychainService.shared.authToken = nil
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

        // Attempt refresh
        guard let url = URL(string: "\(apiBaseURL)/api/v1/auth/refresh") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("PerenniaAI-iOS/1.0 BackgroundSync", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 10

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return false }

            if httpResponse.statusCode == 200 || httpResponse.statusCode == 201 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let newToken = json["access_token"] as? String ?? json["token"] as? String {
                    KeychainService.shared.authToken = newToken
                    logger.info("Token refreshed successfully")
                    return true
                }
            } else if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                // Refresh token is also expired — clear and require re-login
                KeychainService.shared.authToken = nil
                logger.warning("Token refresh failed with \(httpResponse.statusCode) — user must re-login")
                return false
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

        // Update last sync timestamp
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: CacheKey.lastSync)

        return hasNewData
    }

    private func fetchDashboard() async throws -> DashboardData {
        let data = try await apiRequest(path: "/api/v1/dashboard/summary")
        return try decoder.decode(DashboardData.self, from: data)
    }

    private func fetchTasks() async throws -> [TaskItem] {
        let data = try await apiRequest(path: "/api/v1/tasks", queryItems: [
            URLQueryItem(name: "status", value: "pending"),
            URLQueryItem(name: "limit", value: "20"),
            URLQueryItem(name: "sort", value: "due_date")
        ])

        // The API may return tasks in a wrapper object or as a direct array.
        // Try direct array first, then wrapper.
        if let tasks = try? decoder.decode([TaskItem].self, from: data) {
            return tasks
        }

        // Try wrapper: { "tasks": [...] }
        struct TasksWrapper: Codable {
            let tasks: [TaskItem]
        }
        let wrapper = try decoder.decode(TasksWrapper.self, from: data)
        return wrapper.tasks
    }

    private func fetchContacts() async throws -> [CarPlayContact] {
        let data = try await apiRequest(path: "/api/v1/leads", queryItems: [
            URLQueryItem(name: "limit", value: "20"),
            URLQueryItem(name: "sort", value: "last_contacted_at")
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

    private func fetchRateAlerts() async throws -> [RateAlert] {
        let data = try await apiRequest(path: "/api/v1/rate-alerts", queryItems: [
            URLQueryItem(name: "limit", value: "10"),
            URLQueryItem(name: "status", value: "active")
        ])

        if let alerts = try? decoder.decode([RateAlert].self, from: data) {
            return alerts
        }

        struct AlertsWrapper: Codable {
            let alerts: [RateAlert]
        }
        let wrapper = try decoder.decode(AlertsWrapper.self, from: data)
        return wrapper.alerts
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

        let (data, response) = try await session.data(for: request)

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
        case 429:
            logger.warning("Rate limited during background sync")
            throw SyncError.rateLimited
        default:
            logger.error("API error \(httpResponse.statusCode) for \(path)")
            throw SyncError.httpError(statusCode: httpResponse.statusCode)
        }
    }

    // MARK: - Private: Caching

    private func cacheData(dashboard: DashboardData? = nil,
                           tasks: [TaskItem]? = nil,
                           contacts: [CarPlayContact]? = nil,
                           rateAlerts: [RateAlert]? = nil) {
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
    }

    // MARK: - Private: Helpers

    private func shouldSync() -> Bool {
        let lastSync = UserDefaults.standard.double(forKey: CacheKey.lastSync)
        guard lastSync > 0 else { return true }  // Never synced before
        let elapsed = Date().timeIntervalSince1970 - lastSync
        return elapsed >= minimumSyncInterval
    }

    private func dashboardEquals(_ a: DashboardData?, _ b: DashboardData) -> Bool {
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
            case .httpError(let code):
                return "HTTP error \(code)"
            }
        }
    }
}
