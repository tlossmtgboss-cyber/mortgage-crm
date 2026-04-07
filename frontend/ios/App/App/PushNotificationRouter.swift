import UIKit
import CarPlay
import os.log

// MARK: - Notification Names for CarPlay Updates

extension Notification.Name {
    /// Broad notification: any CarPlay-relevant data changed.
    static let carPlayDataDidUpdate = Notification.Name("carPlayDataDidUpdate")

    /// Task data changed (created, updated, completed, deleted).
    static let carPlayTasksDidUpdate = Notification.Name("carPlayTasksDidUpdate")

    /// Lead/contact data changed (created, updated, converted).
    static let carPlayLeadsDidUpdate = Notification.Name("carPlayLeadsDidUpdate")

    /// A rate alert was received or updated.
    static let carPlayRateAlertReceived = Notification.Name("carPlayRateAlertReceived")

    /// An incoming call notification for CarPlay display.
    static let carPlayIncomingCall = Notification.Name("carPlayIncomingCall")

    /// Loan pipeline data changed.
    static let carPlayPipelineDidUpdate = Notification.Name("carPlayPipelineDidUpdate")

    /// An appointment or calendar event changed.
    static let carPlayAppointmentDidUpdate = Notification.Name("carPlayAppointmentDidUpdate")
}

// MARK: - Push Notification Types

/// Known push notification types from the Perennia AI backend.
private enum PushNotificationType: String {
    // Tasks
    case taskCreated = "task_created"
    case taskUpdated = "task_updated"
    case taskCompleted = "task_completed"
    case taskOverdue = "task_overdue"

    // Leads
    case leadCreated = "lead_created"
    case leadUpdated = "lead_updated"
    case leadAssigned = "lead_assigned"
    case leadConverted = "lead_converted"

    // Loans/Pipeline
    case loanStageChanged = "loan_stage_changed"
    case loanUpdated = "loan_updated"
    case documentReceived = "document_received"

    // Rates
    case rateAlert = "rate_alert"
    case rateLockExpiring = "rate_lock_expiring"

    // Communication
    case incomingCall = "incoming_call"
    case missedCall = "missed_call"
    case smsReceived = "sms_received"
    case emailReceived = "email_received"

    // Calendar
    case appointmentReminder = "appointment_reminder"
    case appointmentCreated = "appointment_created"
    case appointmentCancelled = "appointment_cancelled"

    // System
    case complianceAlert = "compliance_alert"
    case systemNotification = "system_notification"
}

// MARK: - PushNotificationRouter

/// Routes incoming push notifications to the appropriate handler based on app state and CarPlay connectivity.
///
/// Routing logic:
/// - If CarPlay is connected: update CarPlay templates directly via NotificationCenter.
/// - If app is in foreground: let Capacitor handle it (existing behavior), but also update caches.
/// - If app is in background: update caches so CarPlay has fresh data on next session.
///
/// This class does NOT modify AppDelegate. The AppDelegate agent integrates this
/// by calling `PushNotificationRouter.shared.routeNotification(userInfo)` from
/// `application(_:didReceiveRemoteNotification:fetchCompletionHandler:)`.
@available(iOS 13.0, *)
final class PushNotificationRouter {

    static let shared = PushNotificationRouter()

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "PushRouter")

    private init() {}

    // MARK: - Public API

    /// Route an incoming push notification to the appropriate handler.
    ///
    /// - Parameters:
    ///   - userInfo: The push notification payload.
    ///   - completionHandler: Optional background fetch completion handler from the OS.
    func routeNotification(_ userInfo: [AnyHashable: Any],
                           completionHandler: ((UIBackgroundFetchResult) -> Void)? = nil) {
        guard let typeString = userInfo["type"] as? String else {
            logger.warning("Push notification missing 'type' field, ignoring")
            completionHandler?(.noData)
            return
        }

        guard let type = PushNotificationType(rawValue: typeString) else {
            logger.info("Unrecognized push notification type: \(typeString)")
            completionHandler?(.noData)
            return
        }

        logger.info("Routing push notification: type=\(typeString), carPlay=\(self.isCarPlayConnected)")

        // Dispatch based on notification category
        switch type {
        // Task notifications
        case .taskCreated, .taskUpdated, .taskCompleted, .taskOverdue:
            handleTaskNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)

        // Lead/contact notifications
        case .leadCreated, .leadUpdated, .leadAssigned, .leadConverted:
            handleLeadNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)

        // Loan/pipeline notifications
        case .loanStageChanged, .loanUpdated, .documentReceived:
            handlePipelineNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)

        // Rate notifications
        case .rateAlert, .rateLockExpiring:
            handleRateNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)

        // Communication notifications
        case .incomingCall:
            handleIncomingCallNotification(userInfo: userInfo, completionHandler: completionHandler)
        case .missedCall, .smsReceived, .emailReceived:
            handleCommunicationNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)

        // Calendar notifications
        case .appointmentReminder, .appointmentCreated, .appointmentCancelled:
            handleAppointmentNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)

        // System notifications
        case .complianceAlert, .systemNotification:
            handleSystemNotification(type: type, userInfo: userInfo, completionHandler: completionHandler)
        }
    }

    // MARK: - CarPlay Connection State

    /// Whether CarPlay is currently connected.
    /// Uses the presence of a CarPlay scene to determine connectivity.
    var isCarPlayConnected: Bool {
        if #available(iOS 14.0, *) {
            return isCarPlaySceneConnected()
        }
        return false
    }

    // MARK: - Task Notifications

    private func handleTaskNotification(type: PushNotificationType,
                                        userInfo: [AnyHashable: Any],
                                        completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling task notification: \(type.rawValue)")

        // Refresh task cache in background
        Task {
            await BackgroundSyncManager.shared.refreshTasks()
            // Also refresh dashboard since task counts may have changed
            await BackgroundSyncManager.shared.refreshDashboard()

            // Notify CarPlay
            await MainActor.run {
                NotificationCenter.default.post(
                    name: .carPlayTasksDidUpdate,
                    object: nil,
                    userInfo: userInfo
                )
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
            }

            completionHandler?(.newData)
        }
    }

    // MARK: - Lead Notifications

    private func handleLeadNotification(type: PushNotificationType,
                                        userInfo: [AnyHashable: Any],
                                        completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling lead notification: \(type.rawValue)")

        Task {
            await BackgroundSyncManager.shared.refreshContacts()
            await BackgroundSyncManager.shared.refreshDashboard()

            await MainActor.run {
                NotificationCenter.default.post(
                    name: .carPlayLeadsDidUpdate,
                    object: nil,
                    userInfo: userInfo
                )
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
            }

            completionHandler?(.newData)
        }
    }

    // MARK: - Pipeline Notifications

    private func handlePipelineNotification(type: PushNotificationType,
                                            userInfo: [AnyHashable: Any],
                                            completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling pipeline notification: \(type.rawValue)")

        Task {
            await BackgroundSyncManager.shared.refreshDashboard()

            await MainActor.run {
                NotificationCenter.default.post(
                    name: .carPlayPipelineDidUpdate,
                    object: nil,
                    userInfo: userInfo
                )
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
            }

            completionHandler?(.newData)
        }
    }

    // MARK: - Rate Notifications

    private func handleRateNotification(type: PushNotificationType,
                                        userInfo: [AnyHashable: Any],
                                        completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling rate notification: \(type.rawValue)")

        Task {
            await BackgroundSyncManager.shared.refreshRateAlerts()
            await BackgroundSyncManager.shared.refreshDashboard()

            await MainActor.run {
                NotificationCenter.default.post(
                    name: .carPlayRateAlertReceived,
                    object: nil,
                    userInfo: userInfo
                )
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
            }

            completionHandler?(.newData)
        }
    }

    // MARK: - Incoming Call

    private func handleIncomingCallNotification(userInfo: [AnyHashable: Any],
                                                completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling incoming call notification")

        // Incoming calls are time-sensitive -- post immediately without waiting for cache refresh.
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: .carPlayIncomingCall,
                object: nil,
                userInfo: userInfo
            )
        }

        completionHandler?(.newData)
    }

    // MARK: - Communication Notifications (SMS, Email, Missed Calls)

    private func handleCommunicationNotification(type: PushNotificationType,
                                                 userInfo: [AnyHashable: Any],
                                                 completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling communication notification: \(type.rawValue)")

        // Refresh contacts since last-contacted timestamps may change
        Task {
            await BackgroundSyncManager.shared.refreshContacts()

            await MainActor.run {
                NotificationCenter.default.post(
                    name: .carPlayLeadsDidUpdate,
                    object: nil,
                    userInfo: userInfo
                )
            }

            completionHandler?(.newData)
        }
    }

    // MARK: - Appointment Notifications

    private func handleAppointmentNotification(type: PushNotificationType,
                                               userInfo: [AnyHashable: Any],
                                               completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling appointment notification: \(type.rawValue)")

        Task {
            await BackgroundSyncManager.shared.refreshDashboard()

            await MainActor.run {
                NotificationCenter.default.post(
                    name: .carPlayAppointmentDidUpdate,
                    object: nil,
                    userInfo: userInfo
                )
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil)
            }

            completionHandler?(.newData)
        }
    }

    // MARK: - System Notifications

    private func handleSystemNotification(type: PushNotificationType,
                                          userInfo: [AnyHashable: Any],
                                          completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling system notification: \(type.rawValue)")

        // System notifications don't require cache refresh but CarPlay may want to display them
        DispatchQueue.main.async {
            NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil, userInfo: userInfo)
        }

        completionHandler?(.noData)
    }
}

// MARK: - CarPlay Scene Check Helper

@available(iOS 14.0, *)
private func isCarPlaySceneConnected() -> Bool {
    return UIApplication.shared.connectedScenes.contains { $0 is CPTemplateApplicationScene }
}
