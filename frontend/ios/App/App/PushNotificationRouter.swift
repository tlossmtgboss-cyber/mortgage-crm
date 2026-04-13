import UIKit
import CarPlay
import Capacitor
import os.log

// MARK: - Notification Names for CarPlay Updates

extension Notification.Name {
    // carPlayDataDidUpdate is defined in AppDelegate.swift

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

    /// Push notification tapped — the WebView should navigate to a deep link path.
    static let pushNotificationDeepLink = Notification.Name("com.perenniaai.crm.pushNotificationDeepLink")
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

// MARK: - Notification Action Identifiers

/// Action identifiers for interactive notification buttons.
enum PushNotificationAction {
    static let completeTask = "COMPLETE_TASK"
    static let callBack = "CALL_BACK"
    static let viewLead = "VIEW_LEAD"
    static let viewLoan = "VIEW_LOAN"
    static let dismiss = "DISMISS"
    static let snooze = "SNOOZE"
}

/// Category identifiers for grouping notification actions.
enum PushNotificationCategory {
    static let task = "TASK_NOTIFICATION"
    static let lead = "LEAD_NOTIFICATION"
    static let loan = "LOAN_NOTIFICATION"
    static let call = "CALL_NOTIFICATION"
    static let appointment = "APPOINTMENT_NOTIFICATION"
    static let rateAlert = "RATE_ALERT_NOTIFICATION"
    static let system = "SYSTEM_NOTIFICATION"
}

// MARK: - PushNotificationRouter

/// Routes incoming push notifications to the appropriate handler based on app state and CarPlay connectivity.
///
/// Routing logic:
/// - If CarPlay is connected: update CarPlay templates directly via NotificationCenter.
/// - If app is in foreground: let Capacitor handle it (existing behavior), but also update caches.
/// - If app is in background: update caches so CarPlay has fresh data on next session.
/// - When user taps a notification: deep link to the relevant screen in the React SPA.
///
/// Integration:
/// - AppDelegate calls `PushNotificationRouter.shared.routeNotification(userInfo:)` from
///   `application(_:didReceiveRemoteNotification:fetchCompletionHandler:)`.
/// - AppDelegate calls `PushNotificationRouter.shared.handleNotificationAction(response:)` from
///   `userNotificationCenter(_:didReceive:withCompletionHandler:)`.
/// - Call `PushNotificationRouter.registerNotificationCategories()` at launch.
@available(iOS 13.0, *)
final class PushNotificationRouter {

    static let shared = PushNotificationRouter()

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "PushRouter")

    /// Weak reference to the Capacitor bridge for deep-link navigation.
    weak var bridge: CAPBridgeProtocol?

    private init() {}

    // MARK: - Notification Categories Registration

    /// Register actionable notification categories. Call once from AppDelegate
    /// `didFinishLaunchingWithOptions` BEFORE requesting notification authorization.
    static func registerNotificationCategories() {
        let completeAction = UNNotificationAction(
            identifier: PushNotificationAction.completeTask,
            title: "Complete Task",
            options: []
        )
        let snoozeAction = UNNotificationAction(
            identifier: PushNotificationAction.snooze,
            title: "Snooze 1 Hour",
            options: []
        )
        let callBackAction = UNNotificationAction(
            identifier: PushNotificationAction.callBack,
            title: "Call Back",
            options: [.foreground]
        )
        let viewLeadAction = UNNotificationAction(
            identifier: PushNotificationAction.viewLead,
            title: "View Lead",
            options: [.foreground]
        )
        let viewLoanAction = UNNotificationAction(
            identifier: PushNotificationAction.viewLoan,
            title: "View Loan",
            options: [.foreground]
        )
        let dismissAction = UNNotificationAction(
            identifier: PushNotificationAction.dismiss,
            title: "Dismiss",
            options: [.destructive]
        )

        let taskCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.task,
            actions: [completeAction, snoozeAction],
            intentIdentifiers: [],
            options: []
        )
        let leadCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.lead,
            actions: [viewLeadAction, dismissAction],
            intentIdentifiers: [],
            options: []
        )
        let loanCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.loan,
            actions: [viewLoanAction, dismissAction],
            intentIdentifiers: [],
            options: []
        )
        let callCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.call,
            actions: [callBackAction, dismissAction],
            intentIdentifiers: [],
            options: []
        )
        let appointmentCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.appointment,
            actions: [snoozeAction, dismissAction],
            intentIdentifiers: [],
            options: []
        )
        let rateAlertCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.rateAlert,
            actions: [dismissAction],
            intentIdentifiers: [],
            options: []
        )
        let systemCategory = UNNotificationCategory(
            identifier: PushNotificationCategory.system,
            actions: [dismissAction],
            intentIdentifiers: [],
            options: []
        )

        UNUserNotificationCenter.current().setNotificationCategories([
            taskCategory, leadCategory, loanCategory, callCategory,
            appointmentCategory, rateAlertCategory, systemCategory
        ])
    }

    // MARK: - Public API

    /// Route an incoming push notification to the appropriate handler.
    /// Call this from both `willPresent` (foreground) and background fetch handlers.
    ///
    /// - Parameters:
    ///   - userInfo: The push notification payload.
    ///   - completionHandler: Optional background fetch completion handler from the OS.
    func routeNotification(_ userInfo: [AnyHashable: Any],
                           completionHandler: ((UIBackgroundFetchResult) -> Void)? = nil) {
        let typeString = userInfo["type"] as? String
            ?? userInfo["category"] as? String

        guard let typeString = typeString else {
            logger.warning("Push notification missing 'type' and 'category' fields, ignoring")
            completionHandler?(.noData)
            return
        }

        guard let type = PushNotificationType(rawValue: typeString) else {
            // Unknown type -- still refresh general data, don't crash
            logger.info("Unrecognized push notification type: \(typeString), performing general refresh")
            handleUnknownNotification(typeString: typeString, userInfo: userInfo, completionHandler: completionHandler)
            return
        }

        logger.info("Routing push notification: type=\(typeString), carPlay=\(self.isCarPlayConnected)")

        // Update badge count
        incrementBadgeCount()

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

    /// Handle a notification action (user tapped a button on the notification).
    /// Call this from `userNotificationCenter(_:didReceive:withCompletionHandler:)`.
    ///
    /// - Parameters:
    ///   - response: The notification response containing the action identifier.
    ///   - completionHandler: The completion handler to call when done.
    func handleNotificationAction(_ response: UNNotificationResponse,
                                  completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo
        let actionIdentifier = response.actionIdentifier

        // Clear badge on any interaction
        clearBadgeCount()

        switch actionIdentifier {
        case UNNotificationDefaultActionIdentifier:
            // User tapped the notification body -- deep link to the relevant screen
            handleNotificationTap(userInfo: userInfo)

        case UNNotificationDismissActionIdentifier:
            // User dismissed -- nothing to do
            break

        case PushNotificationAction.completeTask:
            handleCompleteTaskAction(userInfo: userInfo)

        case PushNotificationAction.callBack:
            handleCallBackAction(userInfo: userInfo)

        case PushNotificationAction.viewLead:
            if let leadId = extractEntityId(from: userInfo) {
                navigateToRoute("/leads/\(leadId)")
            } else {
                navigateToRoute("/leads")
            }

        case PushNotificationAction.viewLoan:
            if let loanId = extractEntityId(from: userInfo) {
                navigateToRoute("/loans/\(loanId)")
            } else {
                navigateToRoute("/loans")
            }

        case PushNotificationAction.snooze:
            handleSnoozeAction(userInfo: userInfo)

        case PushNotificationAction.dismiss:
            break

        default:
            logger.info("Unknown action identifier: \(actionIdentifier)")
        }

        completionHandler()
    }

    // MARK: - Deep Link Resolution

    /// Determine the deep link route for a notification payload.
    ///
    /// Routes map to real screens in the React SPA (verified against App.jsx):
    /// - Tasks: /tasks (list) or /mobile-tasks (mobile)
    /// - Leads: /leads/:id or /leads
    /// - Loans: /loans/:id or /loans
    /// - Pipeline: /loans (pipeline view)
    /// - Rate alerts: /rate-monitor
    /// - Calendar: /calendar or /mobile-calendar
    /// - Calls: /call-intelligence or /mobile-ci
    /// - Email: /email-intelligence
    /// - Compliance: /compliance
    /// - Documents: /smart-docs
    /// - Default: /aria/notifications
    func deepLinkRoute(for userInfo: [AnyHashable: Any]) -> String {
        let typeString = userInfo["type"] as? String
            ?? userInfo["category"] as? String
            ?? ""

        guard let type = PushNotificationType(rawValue: typeString) else {
            // Unknown type -- go to notification center
            return "/aria/notifications"
        }

        let entityId = extractEntityId(from: userInfo)

        switch type {
        case .taskCreated, .taskUpdated, .taskCompleted, .taskOverdue:
            return "/tasks"

        case .leadCreated, .leadUpdated, .leadAssigned:
            if let id = entityId { return "/leads/\(id)" }
            return "/leads"

        case .leadConverted:
            // After conversion, the entity becomes a loan
            if let loanId = userInfo["loan_id"] as? Int ?? (userInfo["loan_id"] as? String).flatMap(Int.init) {
                return "/loans/\(loanId)"
            }
            if let id = entityId { return "/leads/\(id)" }
            return "/leads"

        case .loanStageChanged, .loanUpdated:
            if let id = entityId { return "/loans/\(id)" }
            return "/loans"

        case .documentReceived:
            if let loanId = userInfo["loan_id"] as? Int ?? (userInfo["loan_id"] as? String).flatMap(Int.init) {
                return "/smart-docs/client/\(loanId)"
            }
            return "/smart-docs"

        case .rateAlert, .rateLockExpiring:
            return "/rate-monitor"

        case .incomingCall, .missedCall:
            return "/call-intelligence"

        case .smsReceived:
            if let id = entityId { return "/leads/\(id)" }
            return "/leads"

        case .emailReceived:
            return "/email-intelligence"

        case .appointmentReminder, .appointmentCreated, .appointmentCancelled:
            if let appointmentId = userInfo["appointment_id"] as? String {
                return "/mobile-appointment/\(appointmentId)"
            }
            return "/calendar"

        case .complianceAlert:
            return "/compliance"

        case .systemNotification:
            return "/aria/notifications"
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

    // MARK: - Badge Count Management

    /// Increment the app badge count by 1.
    func incrementBadgeCount() {
        DispatchQueue.main.async {
            let current = UIApplication.shared.applicationIconBadgeNumber
            UIApplication.shared.applicationIconBadgeNumber = current + 1
        }
    }

    /// Clear the app badge count to zero.
    func clearBadgeCount() {
        DispatchQueue.main.async {
            UIApplication.shared.applicationIconBadgeNumber = 0
        }
    }

    /// Set the app badge count to a specific value.
    func setBadgeCount(_ count: Int) {
        DispatchQueue.main.async {
            UIApplication.shared.applicationIconBadgeNumber = max(0, count)
        }
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

            // Notify CarPlay (use names that CarPlaySceneDelegate actually observes)
            await MainActor.run {
                NotificationCenter.default.post(
                    name: Notification.Name("PerenniaTaskUpdated"),
                    object: nil,
                    userInfo: userInfo
                )
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
                    name: Notification.Name("PerenniaLeadUpdated"),
                    object: nil,
                    userInfo: userInfo
                )
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
                    name: Notification.Name("PerenniaRateAlertReceived"),
                    object: nil,
                    userInfo: userInfo
                )
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
                    name: Notification.Name("PerenniaLeadUpdated"),
                    object: nil,
                    userInfo: userInfo
                )
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
                    name: Notification.Name("PerenniaScheduleUpdated"),
                    object: nil,
                    userInfo: userInfo
                )
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

    // MARK: - Unknown Notification Types

    private func handleUnknownNotification(typeString: String,
                                           userInfo: [AnyHashable: Any],
                                           completionHandler: ((UIBackgroundFetchResult) -> Void)?) {
        logger.info("Handling unknown notification type: \(typeString)")

        // Still increment badge for unknown types
        incrementBadgeCount()

        // Refresh dashboard as a safe default
        Task {
            await BackgroundSyncManager.shared.refreshDashboard()

            await MainActor.run {
                NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil, userInfo: userInfo)
            }

            completionHandler?(.noData)
        }
    }

    // MARK: - Notification Tap Handling (Deep Linking)

    /// Handle a tap on a notification body. Resolves the deep link route and navigates.
    private func handleNotificationTap(userInfo: [AnyHashable: Any]) {
        let route = deepLinkRoute(for: userInfo)
        logger.info("Notification tapped, navigating to: \(route)")
        navigateToRoute(route)
    }

    // MARK: - Action Handlers

    /// Mark a task as complete via API (best-effort, fire-and-forget).
    private func handleCompleteTaskAction(userInfo: [AnyHashable: Any]) {
        guard let taskId = extractEntityId(from: userInfo) else {
            logger.warning("Complete task action: no task_id in payload")
            navigateToRoute("/tasks")
            return
        }

        logger.info("Completing task \(taskId) from notification action")

        // Fire-and-forget API call to complete the task
        Task {
            await completeTaskViaAPI(taskId: taskId)
            await BackgroundSyncManager.shared.refreshTasks()
            await BackgroundSyncManager.shared.refreshDashboard()

            await MainActor.run {
                NotificationCenter.default.post(
                    name: Notification.Name("PerenniaTaskUpdated"),
                    object: nil
                )
            }
        }
    }

    /// Initiate a phone call for the "Call Back" action.
    private func handleCallBackAction(userInfo: [AnyHashable: Any]) {
        let phone = userInfo["phone"] as? String
            ?? userInfo["caller_phone"] as? String
            ?? userInfo["phone_number"] as? String

        guard let phone = phone, !phone.isEmpty else {
            logger.warning("Call back action: no phone number in payload")
            // Fall back to navigating to the lead if we have an ID
            if let leadId = extractEntityId(from: userInfo) {
                navigateToRoute("/leads/\(leadId)")
            } else {
                navigateToRoute("/call-intelligence")
            }
            return
        }

        // Clean the phone number and attempt to dial
        let cleaned = phone.replacingOccurrences(of: "[^0-9+]", with: "", options: .regularExpression)
        if let url = URL(string: "tel://\(cleaned)") {
            DispatchQueue.main.async {
                UIApplication.shared.open(url, options: [:]) { success in
                    if !success {
                        // If tel: URL fails, navigate to the contact instead
                        self.navigateToRoute("/call-intelligence")
                    }
                }
            }
        }
    }

    /// Snooze a notification by scheduling a local reminder 1 hour from now.
    private func handleSnoozeAction(userInfo: [AnyHashable: Any]) {
        let title = userInfo["title"] as? String
            ?? (userInfo["aps"] as? [String: Any])?["alert"] as? String
            ?? "Snoozed Reminder"
        let body = userInfo["body"] as? String
            ?? "You snoozed this notification 1 hour ago."

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        // Preserve original userInfo so the snoozed notification can still deep link
        var snoozedInfo = userInfo
        snoozedInfo["snoozed"] = true
        content.userInfo = snoozedInfo

        // Set category so the snoozed notification also has actions
        if let type = userInfo["type"] as? String {
            content.categoryIdentifier = categoryForType(type)
        }

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 3600, repeats: false)
        let request = UNNotificationRequest(
            identifier: "snooze-\(UUID().uuidString)",
            content: content,
            trigger: trigger
        )

        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                self.logger.error("Failed to schedule snoozed notification: \(error.localizedDescription)")
            } else {
                self.logger.info("Notification snoozed for 1 hour")
            }
        }
    }

    // MARK: - Navigation

    /// Navigate the Capacitor WebView to a specific route in the React SPA.
    ///
    /// Uses the same approach as SpotlightHandler: injects JavaScript to push
    /// a route via the History API and dispatches a PopStateEvent so React Router
    /// picks up the navigation.
    func navigateToRoute(_ route: String) {
        logger.info("Navigating to route: \(route)")

        // Post a notification so any native observer can react
        NotificationCenter.default.post(
            name: .pushNotificationDeepLink,
            object: nil,
            userInfo: ["route": route]
        )

        // Sanitize the route to prevent JS injection -- only allow URL-safe characters
        let sanitized = route.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? route

        let js = """
        (function() {
            var route = decodeURIComponent('\(sanitized)');
            if (window.history && window.history.pushState) {
                window.history.pushState({}, '', route);
                window.dispatchEvent(new PopStateEvent('popstate'));
            }
            window.dispatchEvent(new CustomEvent('pushNotificationNavigation', {
                detail: { route: route }
            }));
        })();
        """

        DispatchQueue.main.async { [weak self] in
            guard let bridge = self?.bridge else {
                self?.logger.warning("No Capacitor bridge available for deep link navigation")
                return
            }
            bridge.webView?.evaluateJavaScript(js) { _, error in
                if let error = error {
                    self?.logger.error("Deep link JS navigation error: \(error.localizedDescription)")
                }
            }
        }
    }

    // MARK: - Private Helpers

    /// Extract the primary entity ID from a notification payload.
    /// The backend may send the ID under various keys depending on notification type.
    private func extractEntityId(from userInfo: [AnyHashable: Any]) -> Int? {
        // Try common ID field names in order of specificity
        let idKeys = ["entity_id", "id", "task_id", "lead_id", "loan_id", "appointment_id"]
        for key in idKeys {
            if let intId = userInfo[key] as? Int {
                return intId
            }
            if let stringId = userInfo[key] as? String, let intId = Int(stringId) {
                return intId
            }
        }
        return nil
    }

    /// Map a notification type string to the appropriate category identifier.
    private func categoryForType(_ typeString: String) -> String {
        guard let type = PushNotificationType(rawValue: typeString) else {
            return PushNotificationCategory.system
        }
        switch type {
        case .taskCreated, .taskUpdated, .taskCompleted, .taskOverdue:
            return PushNotificationCategory.task
        case .leadCreated, .leadUpdated, .leadAssigned, .leadConverted:
            return PushNotificationCategory.lead
        case .loanStageChanged, .loanUpdated, .documentReceived:
            return PushNotificationCategory.loan
        case .incomingCall, .missedCall:
            return PushNotificationCategory.call
        case .smsReceived, .emailReceived:
            return PushNotificationCategory.system
        case .rateAlert, .rateLockExpiring:
            return PushNotificationCategory.rateAlert
        case .appointmentReminder, .appointmentCreated, .appointmentCancelled:
            return PushNotificationCategory.appointment
        case .complianceAlert, .systemNotification:
            return PushNotificationCategory.system
        }
    }

    /// Fire-and-forget API call to mark a task as complete.
    private func completeTaskViaAPI(taskId: Int) async {
        guard let token = KeychainService.shared.authToken else {
            logger.warning("No auth token -- cannot complete task via API")
            return
        }

        guard let url = URL(string: "\(APIConfig.apiBaseURL)/api/v1/tasks/\(taskId)/complete") else {
            logger.error("Invalid URL for task completion")
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("PerenniaAI-iOS/PushAction", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 10

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse {
                if (200...299).contains(httpResponse.statusCode) {
                    logger.info("Task \(taskId) marked complete via notification action")
                } else {
                    logger.warning("Task completion returned status \(httpResponse.statusCode)")
                }
            }
        } catch {
            logger.error("Task completion API call failed: \(error.localizedDescription)")
        }
    }
}

// MARK: - CarPlay Scene Check Helper

@available(iOS 14.0, *)
private func isCarPlaySceneConnected() -> Bool {
    return UIApplication.shared.connectedScenes.contains { $0 is CPTemplateApplicationScene }
}
