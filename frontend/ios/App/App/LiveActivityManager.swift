/**
 * LiveActivityManager.swift
 * Perennia AI - Live Activity Lifecycle Manager
 *
 * Manages the lifecycle of loan closing Live Activities:
 * - Start: Creates a new Live Activity for a loan entering the closing pipeline
 * - Update: Pushes stage changes to an active Live Activity
 * - End: Dismisses the activity when a loan reaches a terminal stage
 * - Refresh: Fetches latest loan data from the backend and updates activities
 *
 * Constraints:
 * - iOS 16.2+ required for Live Activities with push token support
 * - iOS limits concurrent activities to 5 per app
 * - Activities auto-expire 8 hours after last update (iOS policy)
 * - Push token support enables server-driven updates via ActivityKit push
 *
 * Usage from Capacitor (via LiveActivityPlugin):
 *   await LiveActivityManager.shared.startClosingActivity(...)
 *   await LiveActivityManager.shared.updateClosingActivity(...)
 *   await LiveActivityManager.shared.endClosingActivity(...)
 */

import Foundation
import ActivityKit
import os.log

// MARK: - Local ClosingStage (mirror of PerenniaWidgets/ClosingActivity.swift)
//
// The canonical ClosingStage lives in the PerenniaWidgets extension target,
// which the main app target cannot import. This local copy provides the
// enum cases, raw-stage initializer, progress, and displayName needed by
// LiveActivityManager. Keep in sync with ClosingActivity.swift.

#if canImport(ActivityKit)

private enum ClosingStage: String, CaseIterable {
    case application = "APPLICATION"
    case processing = "PROCESSING"
    case underwriting = "UNDERWRITING"
    case conditionalApproval = "CONDITIONAL_APPROVAL"
    case ctc = "CTC"
    case clearToClose = "CLEAR_TO_CLOSE"
    case closing = "CLOSING"
    case funded = "FUNDED"

    /// Progress as a fraction (0.0 - 1.0) for this stage.
    var progress: Double {
        guard ClosingStage.allCases.count > 1 else { return 0.0 }
        let index = ClosingStage.allCases.firstIndex(of: self) ?? 0
        return Double(index) / Double(ClosingStage.allCases.count - 1)
    }

    /// Human-readable display name.
    var displayName: String {
        switch self {
        case .application: return "Application"
        case .processing: return "Processing"
        case .underwriting: return "Underwriting"
        case .conditionalApproval: return "Conditional Approval"
        case .ctc: return "Clear to Close"
        case .clearToClose: return "Clear to Close"
        case .closing: return "Closing"
        case .funded: return "Funded"
        }
    }

    /// Initialize from a raw stage string, mapping intermediate stages
    /// to their closest closing pipeline equivalent.
    init?(fromRawStage raw: String) {
        let upper = raw.uppercased()

        // Direct match
        if let direct = ClosingStage(rawValue: upper) {
            self = direct
            return
        }

        // Map intermediate stages that aren't in the closing subset
        switch upper {
        case "DISCLOSED", "SUBMITTED":
            self = .processing
        case "UW_RECEIVED":
            self = .underwriting
        case "APPROVED":
            self = .conditionalApproval
        case "SUSPENDED":
            self = .underwriting  // Suspended goes back to UW review
        case "DOCS", "DOCS_OUT":
            self = .closing
        default:
            return nil
        }
    }
}

#endif

// MARK: - Backend Loan Response Model

/// Lightweight model for decoding loan data from the backend API.
/// Matches the shape returned by GET /api/v1/loans/{loan_id}.
private struct LoanResponse: Codable {
    let id: Int
    let borrowerName: String?
    let amount: Double?
    let stage: String?
    let propertyAddress: String?
    let closingDate: String?
    let predictedCloseDate: String?
    let nextAction: String?

    enum CodingKeys: String, CodingKey {
        case id
        case borrowerName = "borrower_name"
        case amount
        case stage
        case propertyAddress = "property_address"
        case closingDate = "closing_date"
        case predictedCloseDate = "predicted_close_date"
        case nextAction = "next_action"
    }
}

// MARK: - LiveActivityManager

@available(iOS 16.2, *)
final class LiveActivityManager {

    // MARK: - Singleton

    static let shared = LiveActivityManager()
    private init() {
        session = {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 15
            config.timeoutIntervalForResource = 30
            config.waitsForConnectivity = false
            return URLSession(configuration: config)
        }()
    }

    // MARK: - Constants

    /// Maximum concurrent Live Activities allowed by iOS
    private static let maxConcurrentActivities = 5

    /// Default stale policy: Activities without updates expire after this duration.
    /// iOS enforces an 8-hour maximum; we use 8 hours to maximize visibility.
    private static let staleTimeoutHours: Int = 8

    // MARK: - Logger

    private let logger = Logger(
        subsystem: "com.perenniaai.crm",
        category: "LiveActivity"
    )

    // MARK: - Networking

    private let session: URLSession

    // MARK: - Active Activity Tracking

    /// Maps loanId -> Activity<ClosingActivityAttributes>.ID for quick lookup
    private var activeActivityIds: [String: String] = [:]

    // MARK: - Start Activity

    /// Start a new Live Activity for a loan entering the closing pipeline.
    ///
    /// - Parameters:
    ///   - loanId: Unique loan identifier for API correlation
    ///   - borrower: Borrower display name
    ///   - amount: Formatted loan amount (e.g. "$425,000")
    ///   - address: Property address
    ///   - stage: Current loan stage (uppercase string)
    /// - Returns: Dictionary with activity ID and optional push token (hex-encoded)
    @discardableResult
    func startClosingActivity(
        loanId: String,
        borrower: String,
        amount: String,
        address: String,
        stage: String
    ) async -> [String: Any] {
        // Guard: Activities must be enabled by the user
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            logger.warning("Live Activities are disabled by the user")
            return ["error": "Live Activities are disabled in Settings"]
        }

        // Guard: Respect the iOS concurrent activity limit
        let currentCount = Activity<ClosingActivityAttributes>.activities.count
        if currentCount >= Self.maxConcurrentActivities {
            logger.warning("Cannot start activity: \(currentCount) active (max \(Self.maxConcurrentActivities))")
            return ["error": "Maximum of \(Self.maxConcurrentActivities) concurrent activities reached"]
        }

        // If there's already an activity for this loan, update it instead
        if let existingId = activeActivityIds[loanId],
           let existing = Activity<ClosingActivityAttributes>.activities.first(where: { $0.id == existingId }) {
            logger.info("Activity already exists for loan \(loanId), updating instead")
            let closingStage = ClosingStage(fromRawStage: stage)
            let updatedState = ClosingActivityAttributes.ContentState(
                currentStage: stage,
                stageProgress: closingStage?.progress ?? 0.0,
                lastUpdate: Date(),
                nextAction: defaultNextAction(for: stage),
                estimatedClose: nil
            )
            await existing.update(
                ActivityContent(state: updatedState, staleDate: staleDate())
            )
            return [
                "activityId": existing.id,
                "loanId": loanId,
                "updated": true
            ]
        }

        // Resolve the closing stage and compute initial progress
        let closingStage = ClosingStage(fromRawStage: stage)
        let progress = closingStage?.progress ?? 0.0

        let attributes = ClosingActivityAttributes(
            borrowerName: borrower,
            loanAmount: amount,
            propertyAddress: address,
            loanId: loanId
        )

        let initialState = ClosingActivityAttributes.ContentState(
            currentStage: stage,
            stageProgress: progress,
            lastUpdate: Date(),
            nextAction: defaultNextAction(for: stage),
            estimatedClose: nil
        )

        let content = ActivityContent(
            state: initialState,
            staleDate: staleDate()
        )

        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: content,
                pushType: .token
            )

            logger.info("Started Live Activity \(activity.id) for loan \(loanId) at stage \(stage)")
            activeActivityIds[loanId] = activity.id

            // Audit: log activity start
            AuditLogger.shared.log(
                event: .featureAccess,
                details: [
                    "feature": "live_activity",
                    "action": "start",
                    "loanId": loanId,
                    "stage": stage,
                    "activityId": activity.id
                ]
            )

            var result: [String: Any] = [
                "activityId": activity.id,
                "loanId": loanId,
                "stage": stage,
                "progress": progress
            ]

            // Get the initial push token if available
            if let pushToken = activity.pushToken {
                let tokenString = pushToken.map { String(format: "%02x", $0) }.joined()
                result["pushToken"] = tokenString
                logger.info("Push token for loan \(loanId): \(tokenString.prefix(16))...")

                // Register the ActivityKit push token with the backend
                await registerPushTokenWithBackend(
                    loanId: loanId,
                    pushToken: tokenString,
                    activityId: activity.id
                )
            }

            // Start observing push token updates
            Task.detached { [weak self] in
                await self?.observePushTokenUpdates(for: activity, loanId: loanId)
            }

            return result

        } catch {
            logger.error("Failed to start Live Activity for loan \(loanId): \(error.localizedDescription)")
            return ["error": error.localizedDescription]
        }
    }

    // MARK: - Update Activity

    /// Update an active Live Activity with a new loan stage.
    ///
    /// - Parameters:
    ///   - loanId: Loan identifier to look up the activity
    ///   - stage: New loan stage (uppercase string)
    ///   - nextAction: Description of the next step in the process
    ///   - estimatedClose: Optional estimated closing date
    /// - Returns: Dictionary with update status
    @discardableResult
    func updateClosingActivity(
        loanId: String,
        stage: String,
        nextAction: String,
        estimatedClose: Date?
    ) async -> [String: Any] {
        guard let activity = findActivity(for: loanId) else {
            logger.warning("No active Live Activity found for loan \(loanId)")
            return ["error": "No active activity for loan \(loanId)"]
        }

        let closingStage = ClosingStage(fromRawStage: stage)
        let progress = closingStage?.progress ?? 0.0

        let updatedState = ClosingActivityAttributes.ContentState(
            currentStage: stage,
            stageProgress: progress,
            lastUpdate: Date(),
            nextAction: nextAction,
            estimatedClose: estimatedClose
        )

        let content = ActivityContent(
            state: updatedState,
            staleDate: staleDate()
        )

        await activity.update(content)
        logger.info("Updated Live Activity for loan \(loanId) -> \(stage) (\(Int(progress * 100))%)")

        return [
            "activityId": activity.id,
            "loanId": loanId,
            "stage": stage,
            "progress": progress,
            "updated": true
        ]
    }

    // MARK: - End Activity

    /// End a Live Activity when a loan reaches a terminal stage.
    ///
    /// The activity remains visible on the Lock Screen for up to 4 hours
    /// after dismissal (iOS behavior) showing the final state.
    ///
    /// - Parameters:
    ///   - loanId: Loan identifier
    ///   - finalStage: Terminal stage (FUNDED, CANCELLED, DENIED, etc.)
    /// - Returns: Dictionary with dismissal status
    @discardableResult
    func endClosingActivity(
        loanId: String,
        finalStage: String
    ) async -> [String: Any] {
        guard let activity = findActivity(for: loanId) else {
            logger.warning("No active Live Activity found for loan \(loanId) to end")
            return ["error": "No active activity for loan \(loanId)"]
        }

        let isFunded = finalStage.uppercased() == "FUNDED"
        let closingStage = ClosingStage(fromRawStage: finalStage)

        let finalState = ClosingActivityAttributes.ContentState(
            currentStage: finalStage,
            stageProgress: isFunded ? 1.0 : (closingStage?.progress ?? 0.0),
            lastUpdate: Date(),
            nextAction: isFunded
                ? "Loan funded -- congratulations!"
                : "Loan \(finalStage.lowercased())",
            estimatedClose: nil
        )

        let content = ActivityContent(
            state: finalState,
            staleDate: nil
        )

        // Use .default policy: activity lingers on Lock Screen for up to 4 hours
        await activity.end(content, dismissalPolicy: .default)
        activeActivityIds.removeValue(forKey: loanId)

        logger.info("Ended Live Activity for loan \(loanId) with final stage \(finalStage)")

        // Audit: log activity end
        AuditLogger.shared.log(
            event: .featureAccess,
            details: [
                "feature": "live_activity",
                "action": "end",
                "loanId": loanId,
                "finalStage": finalStage,
                "activityId": activity.id
            ]
        )

        return [
            "activityId": activity.id,
            "loanId": loanId,
            "finalStage": finalStage,
            "ended": true
        ]
    }

    // MARK: - End All Activities

    /// End all active closing Live Activities.
    /// Used during logout or app reset.
    func endAllActivities() async {
        let activities = Activity<ClosingActivityAttributes>.activities
        logger.info("Ending all \(activities.count) Live Activities")

        for activity in activities {
            let finalState = ClosingActivityAttributes.ContentState(
                currentStage: activity.content.state.currentStage,
                stageProgress: activity.content.state.stageProgress,
                lastUpdate: Date(),
                nextAction: "Session ended",
                estimatedClose: nil
            )
            let content = ActivityContent(state: finalState, staleDate: nil)
            await activity.end(content, dismissalPolicy: .immediate)
        }

        activeActivityIds.removeAll()
    }

    // MARK: - Refresh from Backend

    /// Fetch latest loan data from the backend and update all active Live Activities.
    /// On network failure, activities retain their current (stale) data -- no crash.
    ///
    /// - Returns: Dictionary with refresh results per loan
    func refreshFromBackend() async -> [String: Any] {
        let activities = Activity<ClosingActivityAttributes>.activities
        guard !activities.isEmpty else {
            return ["refreshed": 0, "message": "No active activities to refresh"]
        }

        guard let token = KeychainService.shared.authToken else {
            logger.warning("No auth token available for Live Activity refresh")
            return ["refreshed": 0, "error": "Not authenticated"]
        }

        var refreshed = 0
        var errors = 0

        for activity in activities {
            let loanId = activity.attributes.loanId
            do {
                let loanData = try await fetchLoanFromBackend(loanId: loanId, token: token)

                let stage = loanData.stage ?? activity.content.state.currentStage
                let closingStage = ClosingStage(fromRawStage: stage)
                let progress = closingStage?.progress ?? activity.content.state.stageProgress

                // Parse estimated close date from backend
                let estimatedClose = parseISO8601Date(loanData.closingDate ?? loanData.predictedCloseDate)

                let updatedState = ClosingActivityAttributes.ContentState(
                    currentStage: stage,
                    stageProgress: progress,
                    lastUpdate: Date(),
                    nextAction: loanData.nextAction ?? defaultNextAction(for: stage),
                    estimatedClose: estimatedClose
                )

                let content = ActivityContent(
                    state: updatedState,
                    staleDate: staleDate()
                )

                // Check if this is a terminal stage
                let terminalStages: Set<String> = [
                    "FUNDED", "CANCELLED", "DENIED", "DEAD",
                    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE"
                ]
                if terminalStages.contains(stage.uppercased()) {
                    await activity.end(content, dismissalPolicy: .default)
                    activeActivityIds.removeValue(forKey: loanId)
                    logger.info("Ended activity for loan \(loanId) -- terminal stage \(stage)")
                } else {
                    await activity.update(content)
                    logger.info("Refreshed activity for loan \(loanId) -> \(stage)")
                }

                refreshed += 1

            } catch {
                // Graceful fallback: keep stale data, log the error, don't crash
                logger.error("Failed to refresh loan \(loanId): \(error.localizedDescription)")
                errors += 1
            }
        }

        return [
            "refreshed": refreshed,
            "errors": errors,
            "total": activities.count
        ]
    }

    // MARK: - Query

    /// Get all currently active closing activities and their states.
    func getActiveActivities() -> [[String: Any]] {
        let activities = Activity<ClosingActivityAttributes>.activities
        return activities.map { activity in
            var info: [String: Any] = [
                "activityId": activity.id,
                "loanId": activity.attributes.loanId,
                "borrowerName": activity.attributes.borrowerName,
                "currentStage": activity.content.state.currentStage,
                "stageProgress": activity.content.state.stageProgress,
                "nextAction": activity.content.state.nextAction
            ]
            if let pushToken = activity.pushToken {
                info["pushToken"] = pushToken.map { String(format: "%02x", $0) }.joined()
            }
            return info
        }
    }

    /// Check whether Live Activities are available and enabled.
    func areActivitiesAvailable() -> [String: Any] {
        let authInfo = ActivityAuthorizationInfo()
        return [
            "areActivitiesEnabled": authInfo.areActivitiesEnabled,
            "frequentPushesEnabled": authInfo.frequentPushesEnabled,
            "activeCount": Activity<ClosingActivityAttributes>.activities.count,
            "maxAllowed": Self.maxConcurrentActivities
        ]
    }

    // MARK: - Private: Backend Communication

    /// Fetch a single loan's data from the backend API.
    /// Uses GET /api/v1/loans/{loanId} which returns the loan dict.
    private func fetchLoanFromBackend(loanId: String, token: String) async throws -> LoanResponse {
        let urlString = "\(APIConfig.apiBaseURL)/api/v1/loans/\(loanId)"
        guard let url = URL(string: urlString) else {
            throw LiveActivityError.invalidURL(urlString)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("PerenniaAI-iOS/LiveActivity", forHTTPHeaderField: "User-Agent")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw LiveActivityError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            let decoder = JSONDecoder()
            return try decoder.decode(LoanResponse.self, from: data)
        case 401, 403:
            throw LiveActivityError.unauthorized
        case 404:
            throw LiveActivityError.loanNotFound(loanId)
        default:
            throw LiveActivityError.serverError(httpResponse.statusCode)
        }
    }

    /// Register an ActivityKit push token with the backend so the server
    /// can send Live Activity updates via APNs.
    /// Uses POST /api/v1/push/register with platform "ios_live_activity".
    /// Fails silently on error -- the activity still works client-side.
    private func registerPushTokenWithBackend(
        loanId: String,
        pushToken: String,
        activityId: String
    ) async {
        guard let token = KeychainService.shared.authToken else {
            logger.warning("No auth token for push token registration")
            return
        }

        guard let url = URL(string: "\(APIConfig.apiBaseURL)/api/v1/push/register") else {
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("PerenniaAI-iOS/LiveActivity", forHTTPHeaderField: "User-Agent")

        let payload: [String: Any] = [
            "device_token": pushToken,
            "platform": "ios",
            "device_name": "Live Activity - Loan \(loanId)",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        ]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
            let (_, response) = try await session.data(for: request)
            if let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) {
                logger.info("Registered Live Activity push token for loan \(loanId)")
            } else {
                logger.warning("Push token registration returned non-200 for loan \(loanId)")
            }
        } catch {
            // Fail silently -- push token registration is best-effort.
            // The Live Activity still works via client-side updates.
            logger.error("Push token registration failed for loan \(loanId): \(error.localizedDescription)")
        }
    }

    // MARK: - Private Helpers

    /// Find an active Activity by loan ID.
    private func findActivity(for loanId: String) -> Activity<ClosingActivityAttributes>? {
        // First try the cached ID for O(1) lookup
        if let cachedId = activeActivityIds[loanId],
           let activity = Activity<ClosingActivityAttributes>.activities.first(where: { $0.id == cachedId }) {
            return activity
        }

        // Fallback: scan all activities by loanId attribute
        if let activity = Activity<ClosingActivityAttributes>.activities.first(where: { $0.attributes.loanId == loanId }) {
            // Re-cache
            activeActivityIds[loanId] = activity.id
            return activity
        }

        // No activity found; clean up stale cache entry
        activeActivityIds.removeValue(forKey: loanId)
        return nil
    }

    /// Calculate the stale date for activity content (8 hours from now).
    private func staleDate() -> Date {
        return Calendar.current.date(
            byAdding: .hour,
            value: Self.staleTimeoutHours,
            to: Date()
        ) ?? Date().addingTimeInterval(8 * 3600)
    }

    /// Provide a default "next action" string based on the current stage.
    private func defaultNextAction(for stage: String) -> String {
        guard let closingStage = ClosingStage(fromRawStage: stage) else {
            return "Processing your loan"
        }

        switch closingStage {
        case .application:
            return "Application under review"
        case .processing:
            return "Processor verifying documents"
        case .underwriting:
            return "Awaiting underwriter review"
        case .conditionalApproval:
            return "Clearing remaining conditions"
        case .ctc, .clearToClose:
            return "Title company preparing documents"
        case .closing:
            return "Scheduling closing appointment"
        case .funded:
            return "Loan funded -- congratulations!"
        }
    }

    /// Parse an ISO 8601 date string into a Date.
    private func parseISO8601Date(_ dateString: String?) -> Date? {
        guard let dateString = dateString else { return nil }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        if let date = formatter.date(from: dateString) {
            return date
        }

        // Retry without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: dateString)
    }

    /// Observe push token updates for an activity.
    /// The push token can change during the activity's lifetime;
    /// new tokens are registered with the backend for server-driven updates
    /// and also broadcast via NotificationCenter for the Capacitor plugin.
    private func observePushTokenUpdates(
        for activity: Activity<ClosingActivityAttributes>,
        loanId: String
    ) async {
        for await pushToken in activity.pushTokenUpdates {
            let tokenString = pushToken.map { String(format: "%02x", $0) }.joined()
            logger.info("Push token updated for loan \(loanId): \(tokenString.prefix(16))...")

            // Register the updated token with the backend
            await registerPushTokenWithBackend(
                loanId: loanId,
                pushToken: tokenString,
                activityId: activity.id
            )

            // Post notification so the Capacitor plugin can forward to JS
            await MainActor.run {
                NotificationCenter.default.post(
                    name: Notification.Name("LiveActivityPushTokenUpdated"),
                    object: nil,
                    userInfo: [
                        "loanId": loanId,
                        "pushToken": tokenString,
                        "activityId": activity.id
                    ]
                )
            }
        }
    }
}

// MARK: - Live Activity Errors

@available(iOS 16.2, *)
extension LiveActivityManager {
    enum LiveActivityError: LocalizedError {
        case invalidURL(String)
        case invalidResponse
        case unauthorized
        case loanNotFound(String)
        case serverError(Int)

        var errorDescription: String? {
            switch self {
            case .invalidURL(let url):
                return "Invalid URL: \(url)"
            case .invalidResponse:
                return "Invalid server response"
            case .unauthorized:
                return "Authentication required"
            case .loanNotFound(let id):
                return "Loan \(id) not found"
            case .serverError(let code):
                return "Server error (\(code))"
            }
        }
    }
}

// MARK: - Pre-iOS 16.2 Stub

/// Provides a no-op fallback for devices running iOS < 16.2 so callers
/// don't need availability checks at every call site.
final class LiveActivityManagerCompat {
    static func isAvailable() -> Bool {
        if #available(iOS 16.2, *) {
            return true
        }
        return false
    }
}
