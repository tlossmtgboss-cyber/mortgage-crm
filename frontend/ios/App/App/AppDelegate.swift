import UIKit
import Capacitor
import UserNotifications
import BackgroundTasks

// MARK: - CarPlay Notification Names

extension Notification.Name {
    /// Posted when a push notification arrives that may be relevant to the CarPlay scene.
    /// The userInfo dictionary contains the original notification payload.
    static let carPlayDataDidUpdate = Notification.Name("com.perenniaai.carplay.dataDidUpdate")

    /// Posted when the session times out so the WebView can redirect to the login screen.
    static let sessionDidTimeout = Notification.Name("com.perenniaai.session.didTimeout")
}

// MARK: - Performance Metrics

/// Lightweight container for app-level performance telemetry.
struct PerformanceMetrics {
    /// Time (in seconds) from process start to didFinishLaunchingWithOptions completion.
    static var appLaunchTime: TimeInterval = 0

    /// Resident memory footprint of the current process (bytes). Returns 0 on failure.
    static var memoryUsage: UInt64 {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size) / 4
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return result == KERN_SUCCESS ? info.resident_size : 0
    }
}

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    // Note: With UIApplicationSceneManifest in Info.plist, the window is created
    // by MainSceneDelegate, not here. This property exists for backward compatibility
    // only (e.g., non-scene fallback on very old iOS).
    var window: UIWindow?

    // MARK: - Launch Time Measurement

    /// Captured as early as possible (static initializer) so we have a baseline.
    private static let processStartTime = CFAbsoluteTimeGetCurrent()

    // MARK: - Application Lifecycle

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {

        // --- Launch Time Measurement ---
        let launchDuration = CFAbsoluteTimeGetCurrent() - Self.processStartTime
        PerformanceMetrics.appLaunchTime = launchDuration
        NSLog("[Performance] App launch time: %.3f seconds", launchDuration)
        AuditLogger.shared.log(event: .appForeground, details: [
            "launch_time_ms": String(format: "%.0f", launchDuration * 1000),
            "memory_bytes": "\(PerformanceMetrics.memoryUsage)"
        ])

        // Register actionable notification categories before requesting authorization
        if #available(iOS 13.0, *) {
            PushNotificationRouter.registerNotificationCategories()
        }

        // Set up push notification delegate
        UNUserNotificationCenter.current().delegate = self

        // Request notification permissions
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
            if let error = error {
                NSLog("[Push] Authorization error: %@", error.localizedDescription)
            }
            if granted {
                DispatchQueue.main.async {
                    application.registerForRemoteNotifications()
                }
            }
        }

        // Register BGTaskScheduler tasks. Must happen in didFinishLaunchingWithOptions,
        // before the app finishes launching, per Apple documentation.
        if #available(iOS 13.0, *) {
            BackgroundSyncManager.shared.registerBackgroundTasks()
        }

        // Note: AppSwitcherGuard, file protection, and PerformanceMonitor setup
        // are handled by MainSceneDelegate, which owns the window in the scene
        // lifecycle. Session timeout is also enforced by MainSceneDelegate.

        return true
    }

    // MARK: - Scene Configuration

    /// Routes scene sessions to the correct delegate class.
    /// - CarPlay scenes -> CarPlaySceneDelegate
    /// - Default window scenes -> MainSceneDelegate (Capacitor WebView + lifecycle)
    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {

        if connectingSceneSession.role == .carTemplateApplication {
            let config = UISceneConfiguration(
                name: "CarPlay Configuration",
                sessionRole: .carTemplateApplication
            )
            if #available(iOS 14.0, *) {
                config.delegateClass = CarPlaySceneDelegate.self
            }
            return config
        }

        // Default: main app window
        let config = UISceneConfiguration(
            name: "Default Configuration",
            sessionRole: connectingSceneSession.role
        )
        config.delegateClass = MainSceneDelegate.self
        return config
    }

    func application(
        _ application: UIApplication,
        didDiscardSceneSessions sceneSessions: Set<UISceneSession>
    ) {
        // Clean up resources for discarded scene sessions if needed.
    }

    // MARK: - Push Notification Registration

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        // Forward to Capacitor
        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Forward to Capacitor
        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
    }

    // MARK: - Silent / Background Push Notifications

    func application(_ application: UIApplication,
                     didReceiveRemoteNotification userInfo: [AnyHashable: Any],
                     fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
        // Route through PushNotificationRouter for cache refresh and CarPlay updates
        if #available(iOS 13.0, *) {
            PushNotificationRouter.shared.routeNotification(userInfo, completionHandler: completionHandler)
        } else {
            completionHandler(.noData)
        }
    }

    // MARK: - UNUserNotificationCenterDelegate

    // Handle notifications when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        let userInfo = notification.request.content.userInfo

        // Route to CarPlay and refresh caches via PushNotificationRouter
        if #available(iOS 13.0, *) {
            PushNotificationRouter.shared.routeNotification(userInfo)
        }

        // Also forward to legacy CarPlay routing
        routeToCarPlayIfRelevant(userInfo: userInfo)

        // Show notification even when app is in foreground
        completionHandler([.banner, .badge, .sound])
    }

    // Handle notification tap and actions
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo

        // Route CarPlay-relevant notifications to the CarPlay scene
        routeToCarPlayIfRelevant(userInfo: userInfo)

        // Handle notification actions and deep linking via PushNotificationRouter
        if #available(iOS 13.0, *) {
            PushNotificationRouter.shared.handleNotificationAction(response) {
                // Forward to Capacitor after our handling is done
                NotificationCenter.default.post(name: Notification.Name("pushNotificationActionPerformed"), object: response)
                completionHandler()
            }
        } else {
            NotificationCenter.default.post(name: Notification.Name("pushNotificationActionPerformed"), object: response)
            completionHandler()
        }
    }

    // MARK: - CarPlay Push Notification Routing

    /// Checks if a push notification is relevant to CarPlay and forwards it to the CarPlay scene.
    /// Relevant categories: new tasks, rate alerts, incoming calls, pipeline updates, appointment reminders.
    private func routeToCarPlayIfRelevant(userInfo: [AnyHashable: Any]) {
        // Basic payload validation -- require at least 'type', 'category', or 'aps' key
        guard userInfo["type"] != nil || userInfo["category"] != nil || userInfo["aps"] != nil else {
            return
        }

        let carPlayCategories: Set<String> = [
            "new_task",
            "rate_alert",
            "incoming_call",
            "pipeline_update",
            "appointment_reminder",
            "lead_assigned",
            "sla_warning"
        ]

        let category = userInfo["category"] as? String ?? userInfo["type"] as? String ?? ""

        if carPlayCategories.contains(category) {
            AuditLogger.shared.log(event: .featureAccess, details: [
                "feature": "push_notification",
                "category": category
            ])
            NotificationCenter.default.post(
                name: .carPlayDataDidUpdate,
                object: nil,
                userInfo: userInfo
            )
        }
    }

    // MARK: - Background Fetch (Legacy Fallback)

    /// Legacy background fetch handler. BGTaskScheduler is the primary mechanism
    /// (registered above). This serves as a fallback and delegates to BackgroundSyncManager.
    func application(_ application: UIApplication, performFetchWithCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
        guard KeychainService.shared.authToken != nil else {
            completionHandler(.noData)
            return
        }

        if #available(iOS 13.0, *) {
            Task {
                let result = await BackgroundSyncManager.shared.performBackgroundFetch()
                completionHandler(result)
            }
        } else {
            completionHandler(.noData)
        }
    }

    // MARK: - Memory Warning

    func applicationDidReceiveMemoryWarning(_ application: UIApplication) {
        if #available(iOS 14.0, *) {
            PerformanceMonitor.shared.recordMemoryWarning()
        }
        NSLog("[Memory] Received memory warning. Current usage: %llu bytes", PerformanceMetrics.memoryUsage)
    }

    // MARK: - Termination

    func applicationWillTerminate(_ application: UIApplication) {
        AuditLogger.shared.log(event: .appTerminated)
    }

    // MARK: - URL & Universal Link Handling

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // Called when the app was launched with a URL (pre-scene or non-scene path).
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

}
