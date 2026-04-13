/**
 * LiveActivityPlugin.swift
 * Perennia AI - Capacitor Plugin for Live Activity Management
 *
 * Bridges LiveActivityManager to the React/Capacitor JavaScript layer.
 * Exposes methods to start, update, end, refresh, and query Live Activities
 * for loan closing status.
 *
 * JS usage (via Capacitor):
 *   import { registerPlugin } from '@capacitor/core';
 *   const LiveActivity = registerPlugin('LiveActivity');
 *
 *   // Start
 *   const result = await LiveActivity.startClosingActivity({
 *     loanId: 'abc-123',
 *     borrowerName: 'John Smith',
 *     loanAmount: '$425,000',
 *     propertyAddress: '123 Main St, Charleston, SC',
 *     currentStage: 'UNDERWRITING'
 *   });
 *
 *   // Update
 *   await LiveActivity.updateClosingActivity({
 *     loanId: 'abc-123',
 *     currentStage: 'CTC',
 *     nextAction: 'Title company preparing docs',
 *     estimatedClose: '2026-04-21T00:00:00Z'
 *   });
 *
 *   // Refresh all from backend
 *   await LiveActivity.refreshFromBackend();
 *
 *   // End
 *   await LiveActivity.endClosingActivity({
 *     loanId: 'abc-123',
 *     finalStage: 'FUNDED'
 *   });
 */

import Foundation
import Capacitor
import ActivityKit

@objc(LiveActivityPlugin)
public class LiveActivityPlugin: CAPPlugin, CAPBridgedPlugin {

    // MARK: - CAPBridgedPlugin Conformance

    public let identifier = "LiveActivityPlugin"
    public let jsName = "LiveActivity"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "startClosingActivity", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "updateClosingActivity", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "endClosingActivity", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "endAllActivities", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getActiveActivities", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "refreshFromBackend", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "checkAvailability", returnType: CAPPluginReturnPromise)
    ]

    // MARK: - Push Token Observer

    private var pushTokenObserver: NSObjectProtocol?

    public override func load() {
        // Listen for push token updates from LiveActivityManager and forward to JS
        pushTokenObserver = NotificationCenter.default.addObserver(
            forName: Notification.Name("LiveActivityPushTokenUpdated"),
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let userInfo = notification.userInfo,
                  let loanId = userInfo["loanId"] as? String,
                  let pushToken = userInfo["pushToken"] as? String,
                  let activityId = userInfo["activityId"] as? String else {
                return
            }

            self?.notifyListeners("pushTokenUpdated", data: [
                "loanId": loanId,
                "pushToken": pushToken,
                "activityId": activityId
            ])
        }
    }

    deinit {
        if let observer = pushTokenObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    // MARK: - Start Closing Activity

    /// Start a new Live Activity for a loan.
    ///
    /// Parameters (from JS call):
    ///   - loanId: String (required)
    ///   - borrowerName: String (required)
    ///   - loanAmount: String (required)
    ///   - propertyAddress: String (required)
    ///   - currentStage: String (required)
    ///
    /// Returns: { activityId, loanId, stage, progress, pushToken? } or { error }
    @objc func startClosingActivity(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("Live Activities require iOS 16.2 or later")
            return
        }

        guard let loanId = call.getString("loanId"),
              let borrowerName = call.getString("borrowerName"),
              let loanAmount = call.getString("loanAmount"),
              let propertyAddress = call.getString("propertyAddress"),
              let currentStage = call.getString("currentStage") else {
            call.reject(
                "Missing required parameters",
                "MISSING_PARAMS",
                nil,
                ["required": ["loanId", "borrowerName", "loanAmount", "propertyAddress", "currentStage"]]
            )
            return
        }

        Task {
            let result = await LiveActivityManager.shared.startClosingActivity(
                loanId: loanId,
                borrower: borrowerName,
                amount: loanAmount,
                address: propertyAddress,
                stage: currentStage
            )

            if let error = result["error"] as? String {
                call.reject(error, "ACTIVITY_START_FAILED")
            } else {
                call.resolve(self.sanitizeForJS(result))
            }
        }
    }

    // MARK: - Update Closing Activity

    /// Update an existing Live Activity with a new stage.
    ///
    /// Parameters (from JS call):
    ///   - loanId: String (required)
    ///   - currentStage: String (required)
    ///   - nextAction: String (optional, defaults to stage-appropriate text)
    ///   - estimatedClose: String (optional, ISO 8601 date)
    ///
    /// Returns: { activityId, loanId, stage, progress, updated } or { error }
    @objc func updateClosingActivity(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("Live Activities require iOS 16.2 or later")
            return
        }

        guard let loanId = call.getString("loanId"),
              let currentStage = call.getString("currentStage") else {
            call.reject(
                "Missing required parameters",
                "MISSING_PARAMS",
                nil,
                ["required": ["loanId", "currentStage"]]
            )
            return
        }

        let nextAction = call.getString("nextAction") ?? defaultNextAction(for: currentStage)
        let estimatedClose = parseISO8601Date(call.getString("estimatedClose"))

        Task {
            let result = await LiveActivityManager.shared.updateClosingActivity(
                loanId: loanId,
                stage: currentStage,
                nextAction: nextAction,
                estimatedClose: estimatedClose
            )

            if let error = result["error"] as? String {
                call.reject(error, "ACTIVITY_UPDATE_FAILED")
            } else {
                call.resolve(self.sanitizeForJS(result))
            }
        }
    }

    // MARK: - End Closing Activity

    /// End a Live Activity when a loan reaches a terminal stage.
    ///
    /// Parameters (from JS call):
    ///   - loanId: String (required)
    ///   - finalStage: String (required, e.g. "FUNDED", "CANCELLED")
    ///
    /// Returns: { activityId, loanId, finalStage, ended } or { error }
    @objc func endClosingActivity(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("Live Activities require iOS 16.2 or later")
            return
        }

        guard let loanId = call.getString("loanId"),
              let finalStage = call.getString("finalStage") else {
            call.reject(
                "Missing required parameters",
                "MISSING_PARAMS",
                nil,
                ["required": ["loanId", "finalStage"]]
            )
            return
        }

        Task {
            let result = await LiveActivityManager.shared.endClosingActivity(
                loanId: loanId,
                finalStage: finalStage
            )

            if let error = result["error"] as? String {
                call.reject(error, "ACTIVITY_END_FAILED")
            } else {
                call.resolve(self.sanitizeForJS(result))
            }
        }
    }

    // MARK: - End All Activities

    /// End all active Live Activities (used during logout).
    ///
    /// Returns: { ended: true, count: N }
    @objc func endAllActivities(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("Live Activities require iOS 16.2 or later")
            return
        }

        Task {
            let count = Activity<ClosingActivityAttributes>.activities.count
            await LiveActivityManager.shared.endAllActivities()

            call.resolve([
                "ended": true,
                "count": count
            ])
        }
    }

    // MARK: - Get Active Activities

    /// List all currently active Live Activities.
    ///
    /// Returns: { activities: [{ activityId, loanId, borrowerName, currentStage, ... }] }
    @objc func getActiveActivities(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.resolve(["activities": []])
            return
        }

        let activities = LiveActivityManager.shared.getActiveActivities()
        call.resolve(["activities": activities.map { sanitizeForJS($0) }])
    }

    // MARK: - Refresh from Backend

    /// Fetch latest data from the backend for all active Live Activities.
    /// Activities that fail to refresh keep their stale data (graceful degradation).
    ///
    /// Returns: { refreshed: N, errors: N, total: N }
    @objc func refreshFromBackend(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.resolve(["refreshed": 0, "error": "Live Activities require iOS 16.2 or later"])
            return
        }

        Task {
            let result = await LiveActivityManager.shared.refreshFromBackend()
            call.resolve(self.sanitizeForJS(result))
        }
    }

    // MARK: - Check Availability

    /// Check whether Live Activities are available and enabled on this device.
    ///
    /// Returns: {
    ///   available: Bool,          // iOS 16.2+ device
    ///   areActivitiesEnabled: Bool, // User has not disabled in Settings
    ///   frequentPushesEnabled: Bool,
    ///   activeCount: Int,
    ///   maxAllowed: Int
    /// }
    @objc func checkAvailability(_ call: CAPPluginCall) {
        var result: [String: Any] = [
            "available": LiveActivityManagerCompat.isAvailable()
        ]

        if #available(iOS 16.2, *) {
            let info = LiveActivityManager.shared.areActivitiesAvailable()
            for (key, value) in info {
                result[key] = value
            }
        } else {
            result["areActivitiesEnabled"] = false
            result["frequentPushesEnabled"] = false
            result["activeCount"] = 0
            result["maxAllowed"] = 5
        }

        call.resolve(sanitizeForJS(result))
    }

    // MARK: - Private Helpers

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

    /// Provide a default next-action string for a given stage.
    private func defaultNextAction(for stage: String) -> String {
        let upper = stage.uppercased()
        switch upper {
        case "APPLICATION":
            return "Application under review"
        case "PROCESSING":
            return "Processor verifying documents"
        case "UNDERWRITING":
            return "Awaiting underwriter review"
        case "CONDITIONAL_APPROVAL":
            return "Clearing remaining conditions"
        case "CTC", "CLEAR_TO_CLOSE":
            return "Title company preparing documents"
        case "CLOSING":
            return "Scheduling closing appointment"
        case "FUNDED":
            return "Loan funded -- congratulations!"
        case "CANCELLED", "DENIED", "WITHDRAWN":
            return "Loan \(upper.lowercased())"
        default:
            return "Processing your loan"
        }
    }

    /// Ensure all dictionary values are Capacitor-safe types.
    /// CAPPluginCall.resolve() requires [String: Any] where values are
    /// String, Int, Double, Bool, Array, or Dictionary (no custom types).
    private func sanitizeForJS(_ dict: [String: Any]) -> [String: Any] {
        var sanitized: [String: Any] = [:]
        for (key, value) in dict {
            switch value {
            case let string as String:
                sanitized[key] = string
            case let int as Int:
                sanitized[key] = int
            case let double as Double:
                sanitized[key] = double
            case let bool as Bool:
                sanitized[key] = bool
            case let array as [Any]:
                sanitized[key] = array
            case let nested as [String: Any]:
                sanitized[key] = sanitizeForJS(nested)
            default:
                sanitized[key] = String(describing: value)
            }
        }
        return sanitized
    }
}
