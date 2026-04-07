import UIKit
import Capacitor
import UserNotifications

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

    var window: UIWindow?

    // MARK: - Launch Time Measurement

    /// Captured as early as possible (static initializer) so we have a baseline.
    private static let processStartTime = CFAbsoluteTimeGetCurrent()

    // MARK: - Session Timeout

    /// How long the app may remain inactive before the session is invalidated.
    /// Default: 15 minutes. Clamped between 1 minute and 1 hour.
    private var sessionTimeoutSeconds: TimeInterval = 900

    /// UserDefaults key for persisting the last-active timestamp.
    private static let lastActiveTimeKey = "com.perenniaai.session.lastActiveTime"

    /// Update the session timeout interval (e.g. from MDM configuration).
    /// The value is clamped to [60, 3600] seconds.
    func updateSessionTimeout(_ seconds: TimeInterval) {
        sessionTimeoutSeconds = max(60, min(3600, seconds))
    }

    /// Persist the current time as the last-active timestamp.
    private func recordLastActiveTime() {
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: Self.lastActiveTimeKey)
    }

    /// Check whether the session has exceeded the timeout since the last recorded active time.
    /// If so, clear the auth token, post a notification, and log the event.
    private func enforceSessionTimeoutIfNeeded() {
        let lastActive = UserDefaults.standard.double(forKey: Self.lastActiveTimeKey)
        // If there's no recorded time yet (first launch or cleared), skip enforcement.
        guard lastActive > 0 else { return }

        let elapsed = Date().timeIntervalSince1970 - lastActive
        guard elapsed > sessionTimeoutSeconds else { return }

        // Only enforce if there is actually a session to invalidate.
        guard KeychainService.shared.authToken != nil else { return }

        // Invalidate the session.
        KeychainService.shared.authToken = nil

        // Log the timeout event.
        AuditLogger.shared.log(event: .sessionEnd, details: [
            "reason": "session_timeout",
            "elapsed_seconds": String(format: "%.0f", elapsed),
            "timeout_threshold": String(format: "%.0f", sessionTimeoutSeconds)
        ])

        NSLog("[SessionTimeout] Session invalidated after %.0f seconds of inactivity (threshold: %.0f)", elapsed, sessionTimeoutSeconds)

        // Notify observers (the WebView bridge listens for this to redirect to login).
        NotificationCenter.default.post(name: .sessionDidTimeout, object: nil)
    }

    // MARK: - Application Lifecycle

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Override point for customization after application launch.

        // --- Launch Time Measurement ---
        let launchDuration = CFAbsoluteTimeGetCurrent() - Self.processStartTime
        PerformanceMetrics.appLaunchTime = launchDuration
        NSLog("[Performance] App launch time: %.3f seconds", launchDuration)
        AuditLogger.shared.log(event: .appForeground, details: [
            "launch_time_ms": String(format: "%.0f", launchDuration * 1000),
            "memory_bytes": "\(PerformanceMetrics.memoryUsage)"
        ])

        // Install app-switcher blur overlay to protect sensitive data
        if let window = self.window {
            AppSwitcherGuard.shared.install(on: window)
        }

        // Log app launch
        AuditLogger.shared.log(event: .appForeground)

        // Set file protection for data at rest
        try? FileManager.default.setAttributes(
            [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: NSHomeDirectory()
        )

        // Set up push notification delegate
        UNUserNotificationCenter.current().delegate = self

        // Request notification permissions
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
            if granted {
                DispatchQueue.main.async {
                    application.registerForRemoteNotifications()
                }
            }
        }

        // Enable background fetch for CarPlay data refresh
        application.setMinimumBackgroundFetchInterval(UIApplication.backgroundFetchIntervalMinimum)

        return true
    }

    // MARK: - Multi-Scene Configuration

    /// Returns the correct scene configuration for CarPlay vs the main app window.
    /// The system calls this when a new scene session is being created.
    func application(_ application: UIApplication,
                     configurationForConnecting connectingSceneSession: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        if connectingSceneSession.role == .carTemplateApplication {
            let config = UISceneConfiguration(name: "CarPlay Configuration", sessionRole: .carTemplateApplication)
            if #available(iOS 14.0, *) {
                config.delegateClass = CarPlaySceneDelegate.self
            }
            return config
        }

        let config = UISceneConfiguration(name: "Default Configuration", sessionRole: .windowApplication)
        return config
    }

    /// Called when the user discards a scene session (e.g., swiping away from the app switcher).
    func application(_ application: UIApplication,
                     didDiscardSceneSessions sceneSessions: Set<UISceneSession>) {
        // Release any resources specific to the discarded scenes.
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

    // MARK: - UNUserNotificationCenterDelegate

    // Handle notifications when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Route CarPlay-relevant notifications to the CarPlay scene
        routeToCarPlayIfRelevant(userInfo: notification.request.content.userInfo)

        // Show notification even when app is in foreground
        completionHandler([.banner, .badge, .sound])
    }

    // Handle notification tap
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        // Route CarPlay-relevant notifications to the CarPlay scene
        routeToCarPlayIfRelevant(userInfo: response.notification.request.content.userInfo)

        // Forward to Capacitor
        NotificationCenter.default.post(name: Notification.Name("pushNotificationActionPerformed"), object: response)
        completionHandler()
    }

    // MARK: - CarPlay Push Notification Routing

    /// Checks if a push notification is relevant to CarPlay and forwards it to the CarPlay scene.
    /// Relevant categories: new tasks, rate alerts, incoming calls, pipeline updates, appointment reminders.
    private func routeToCarPlayIfRelevant(userInfo: [AnyHashable: Any]) {
        // Basic payload validation — require at least 'type', 'category', or 'aps' key
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

    // MARK: - Background Fetch for CarPlay Data

    func application(_ application: UIApplication, performFetchWithCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
        // Refresh CarPlay data in background so the CarPlay scene stays current
        guard #available(iOS 14.0, *) else {
            completionHandler(.noData)
            return
        }

        // Verify auth token exists before making network requests
        guard KeychainService.shared.authToken != nil else {
            completionHandler(.noData)
            return
        }

        Task {
            do {
                _ = try await CarPlayAPIService.shared.fetchDashboard()
                AuditLogger.shared.log(event: .dataAccess, details: ["source": "background_fetch"])
                // Notify CarPlay scene that fresh data is available
                await MainActor.run {
                    NotificationCenter.default.post(name: .carPlayDataDidUpdate, object: nil, userInfo: ["source": "background_fetch"])
                }
                completionHandler(.newData)
            } catch {
                completionHandler(.failed)
            }
        }
    }

    // MARK: - Standard Lifecycle Callbacks

    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state. This can occur for certain types of temporary interruptions (such as an incoming phone call or SMS message) or when the user quits the application and it begins the transition to the background state.
        // Use this method to pause ongoing tasks, disable timers, and invalidate graphics rendering callbacks. Games should use this method to pause the game.

        // Record the time the app became inactive for session timeout enforcement.
        recordLastActiveTime()
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // Use this method to release shared resources, save user data, invalidate timers, and store enough application state information to restore your application to its current state in case it is terminated later.
        // If your application supports background execution, this method is called instead of applicationWillTerminate: when the user quits.

        // Flush audit logs to backend before backgrounding
        Task { await AuditLogger.shared.syncToBackend() }
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Restart any tasks that were paused (or not yet started) while the application was inactive. If the application was previously in the background, optionally refresh the user interface.

        // Check whether the session has expired while the app was inactive/backgrounded.
        enforceSessionTimeoutIfNeeded()
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
        AuditLogger.shared.log(event: .appTerminated)
    }

    // MARK: - URL & Universal Link Handling

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // Called when the app was launched with a url. Feel free to add additional processing here,
        // but if you want the App API to support tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        // Feel free to add additional processing here, but if you want the App API to support
        // tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

}
