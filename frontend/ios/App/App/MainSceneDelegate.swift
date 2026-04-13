/**
 * MainSceneDelegate.swift
 * Perennia AI — Main Window Scene Delegate
 *
 * Handles the UIWindowScene lifecycle for the main app window.
 *
 * When UIApplicationSceneManifest is present in Info.plist, iOS ignores the
 * traditional AppDelegate lifecycle callbacks (applicationWillResignActive,
 * applicationDidBecomeActive, etc.) and routes them here instead.
 *
 * Responsibilities:
 *   - Window creation and Capacitor ViewController setup
 *   - Session timeout enforcement (on foreground resume)
 *   - Last-active timestamp recording (on resign active / background)
 *   - Background audit log flush
 *   - AppSwitcherGuard installation (once window is available)
 *   - SpotlightIndexer and PerformanceMonitor integration
 */

import UIKit
import Capacitor
import LocalAuthentication

class MainSceneDelegate: UIResponder, UIWindowSceneDelegate {

    var window: UIWindow?

    // MARK: - Session Timeout

    /// How long the app may remain inactive before the session is invalidated.
    private var sessionTimeoutSeconds: TimeInterval = 900  // 15 minutes

    /// UserDefaults key for persisting the last-active timestamp.
    /// Shared with AppDelegate for backward compatibility.
    private static let lastActiveTimeKey = "com.perenniaai.session.lastActiveTime"

    // MARK: - Scene Lifecycle

    func scene(
        _ scene: UIScene,
        willConnectTo session: UISceneSession,
        options connectionOptions: UIScene.ConnectionOptions
    ) {
        guard let windowScene = scene as? UIWindowScene else { return }

        let window = UIWindow(windowScene: windowScene)
        let viewController = PerenniaViewController()
        window.rootViewController = viewController
        self.window = window
        window.makeKeyAndVisible()

        // Install app-switcher blur overlay now that the window exists
        AppSwitcherGuard.shared.install(on: window)

        // Set file protection for data at rest
        try? FileManager.default.setAttributes(
            [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: NSHomeDirectory()
        )

        // Handle any URLs passed at launch
        for urlContext in connectionOptions.urlContexts {
            _ = ApplicationDelegateProxy.shared.application(
                UIApplication.shared,
                open: urlContext.url,
                options: [:]
            )
        }

        // Handle any user activities passed at launch (universal links)
        if let userActivity = connectionOptions.userActivities.first {
            _ = ApplicationDelegateProxy.shared.application(
                UIApplication.shared,
                continue: userActivity,
                restorationHandler: { _ in }
            )
        }

        // Start Spotlight indexing (throttled internally to 30 min)
        SpotlightIndexer.shared.indexAllData()

        // Start performance monitoring
        if #available(iOS 14.0, *) {
            PerformanceMonitor.shared.recordAppLaunch()
            PerformanceMonitor.shared.startPeriodicMonitoring()
        }
    }

    func sceneDidDisconnect(_ scene: UIScene) {
        // Release resources. The scene may reconnect later.
        if #available(iOS 14.0, *) {
            PerformanceMonitor.shared.stopPeriodicMonitoring()
        }
    }

    func sceneDidBecomeActive(_ scene: UIScene) {
        // Check whether the session has expired while the app was backgrounded.
        enforceSessionTimeoutIfNeeded()

        // Biometric re-auth if returning from extended background
        BiometricAuthManager.shared.authenticateIfNeeded { success in
            if !success {
                NSLog("[BiometricAuth] Authentication failed or cancelled — blur remains")
            }
        }

        // Trigger Spotlight re-index if enough time has passed
        if SpotlightIndexer.shared.shouldReindex {
            SpotlightIndexer.shared.indexAllData()
        }

        // Start periodic audit log sync to prevent data loss on crash
        AuditLogger.shared.startForegroundSync()
    }

    func sceneWillResignActive(_ scene: UIScene) {
        // Record the time the app became inactive for session timeout enforcement.
        recordLastActiveTime()
    }

    func sceneDidEnterBackground(_ scene: UIScene) {
        // Stop foreground periodic sync timer
        AuditLogger.shared.stopForegroundSync()

        // Flush audit logs to backend before backgrounding
        Task { await AuditLogger.shared.syncToBackend() }

        // Schedule background refresh
        if #available(iOS 13.0, *) {
            BackgroundSyncManager.shared.scheduleBackgroundRefresh()
        }
    }

    func sceneWillEnterForeground(_ scene: UIScene) {
        // Resuming from background -- session timeout check happens in sceneDidBecomeActive
    }

    // MARK: - URL & Universal Link Handling (Scene-based)

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        for context in URLContexts {
            _ = ApplicationDelegateProxy.shared.application(
                UIApplication.shared,
                open: context.url,
                options: [:]
            )
        }
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        _ = ApplicationDelegateProxy.shared.application(
            UIApplication.shared,
            continue: userActivity,
            restorationHandler: { _ in }
        )
    }

    // MARK: - Session Timeout (Private)

    private func recordLastActiveTime() {
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: Self.lastActiveTimeKey)
    }

    private func enforceSessionTimeoutIfNeeded() {
        let lastActive = UserDefaults.standard.double(forKey: Self.lastActiveTimeKey)
        guard lastActive > 0 else { return }

        let elapsed = Date().timeIntervalSince1970 - lastActive
        guard elapsed > sessionTimeoutSeconds else { return }

        guard KeychainService.shared.authToken != nil else { return }

        // Invalidate the session
        KeychainService.shared.authToken = nil

        AuditLogger.shared.log(event: .sessionEnd, details: [
            "reason": "session_timeout",
            "elapsed_seconds": String(format: "%.0f", elapsed),
            "timeout_threshold": String(format: "%.0f", sessionTimeoutSeconds)
        ])

        NSLog("[SessionTimeout] Session invalidated after %.0f seconds of inactivity (threshold: %.0f)", elapsed, sessionTimeoutSeconds)

        NotificationCenter.default.post(name: .sessionDidTimeout, object: nil)
    }
}
