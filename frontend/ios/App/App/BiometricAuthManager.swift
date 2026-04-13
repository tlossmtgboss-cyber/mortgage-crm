/**
 * BiometricAuthManager.swift
 * Perennia AI — Biometric Re-Authentication on Foreground Resume
 *
 * Enterprise security requirement: when the app returns from background
 * after a configurable idle period, prompt for Face ID / Touch ID before
 * showing sensitive data. Falls back to device passcode if biometrics
 * are unavailable or not enrolled.
 *
 * Integration: MainSceneDelegate calls `authenticateIfNeeded()` in
 * `sceneDidBecomeActive`. The manager coordinates with AppSwitcherGuard
 * to keep the blur overlay visible until authentication succeeds.
 */

import Foundation
import LocalAuthentication
import UIKit
import Capacitor
import os.log

@MainActor
final class BiometricAuthManager {

    // MARK: - Singleton

    static let shared = BiometricAuthManager()

    // MARK: - Configuration

    /// Minimum background time (seconds) before requiring re-auth.
    /// Short enough for security, long enough to avoid annoyance on
    /// quick app switches (e.g., copying a phone number).
    var reauthThresholdSeconds: TimeInterval = 30

    /// Whether biometric re-auth is enabled. Can be toggled by MDM config
    /// or user preference.
    var isEnabled: Bool = true

    // MARK: - State

    /// Whether we're currently showing a biometric prompt (prevents double-fire).
    private var isAuthenticating = false

    /// Whether the last biometric auth succeeded (reset on background).
    private(set) var isAuthenticated = false

    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "BiometricAuth")

    // MARK: - Init

    private init() {
        // Listen for background transitions to reset auth state
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appDidEnterBackground),
            name: UIApplication.didEnterBackgroundNotification,
            object: nil
        )
    }

    // MARK: - Public API

    /// Check whether biometric authentication is available on this device.
    var biometricType: LABiometryType {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            return .none
        }
        return context.biometryType
    }

    /// Human-readable name for the biometric type (for UI strings).
    var biometricName: String {
        switch biometricType {
        case .faceID:    return "Face ID"
        case .touchID:   return "Touch ID"
        case .opticID:   return "Optic ID"
        @unknown default: return "Biometrics"
        }
    }

    /// Call from `sceneDidBecomeActive`. Evaluates whether re-auth is needed
    /// based on how long the app was backgrounded, then prompts if required.
    ///
    /// - Parameter completion: Called with `true` if auth succeeds or is not needed,
    ///   `false` if the user fails/cancels authentication.
    func authenticateIfNeeded(completion: @escaping (Bool) -> Void) {
        guard isEnabled else {
            isAuthenticated = true
            completion(true)
            return
        }

        // No session = no need for biometric (user will see login screen)
        guard KeychainService.shared.authToken != nil else {
            isAuthenticated = true
            completion(true)
            return
        }

        // Check how long we've been backgrounded
        let lastActive = UserDefaults.standard.double(forKey: "com.perenniaai.session.lastActiveTime")
        if lastActive > 0 {
            let elapsed = Date().timeIntervalSince1970 - lastActive
            if elapsed < reauthThresholdSeconds {
                // Short absence — no re-auth needed
                isAuthenticated = true
                completion(true)
                return
            }
        }

        // Already authenticated this foreground cycle
        if isAuthenticated {
            completion(true)
            return
        }

        // Prevent double prompts
        guard !isAuthenticating else {
            completion(false)
            return
        }

        promptBiometric(completion: completion)
    }

    // MARK: - Private

    private func promptBiometric(completion: @escaping (Bool) -> Void) {
        isAuthenticating = true

        // Rate-limit biometric prompts — block access if exceeded
        guard RateLimiter.biometric.allowAction() else {
            os_log(.error, log: log, "Biometric rate limit exceeded — blocking access")
            AuditLogger.shared.log(event: .biometricFailure, details: [
                "reason": "rate_limited"
            ])
            isAuthenticating = false
            isAuthenticated = false
            setWebViewInteraction(enabled: false)
            completion(false)
            return
        }

        // Disable WebView interaction while biometric prompt is showing
        setWebViewInteraction(enabled: false)

        let context = LAContext()
        context.localizedCancelTitle = "Use Password"

        // Try biometrics first, fall back to device passcode
        let policy: LAPolicy = .deviceOwnerAuthentication
        let reason = "Verify your identity to access Perennia AI"

        AuditLogger.shared.log(event: .biometricPrompt, details: [
            "type": biometricName
        ])

        context.evaluatePolicy(policy, localizedReason: reason) { [weak self] success, error in
            guard let self = self else { return }

            DispatchQueue.main.async {
                self.isAuthenticating = false

                if success {
                    self.isAuthenticated = true
                    AuditLogger.shared.log(event: .biometricSuccess, details: [
                        "type": self.biometricName
                    ])
                    os_log(.info, log: self.log, "Biometric auth succeeded")
                    // Re-enable WebView interaction and remove blur overlay
                    self.setWebViewInteraction(enabled: true)
                    AppSwitcherGuard.shared.removeBiometricHold()
                    completion(true)
                } else {
                    let errorCode = (error as? LAError)?.code ?? .authenticationFailed
                    AuditLogger.shared.log(event: .biometricFailure, details: [
                        "type": self.biometricName,
                        "error": error?.localizedDescription ?? "unknown",
                        "code": "\(errorCode.rawValue)"
                    ])
                    os_log(.error, log: self.log, "Biometric auth failed: %{public}@",
                           error?.localizedDescription ?? "unknown")

                    switch errorCode {
                    case .userCancel, .appCancel, .systemCancel:
                        // User cancelled — keep blur, they can try again
                        completion(false)
                    case .userFallback:
                        // User tapped "Use Password" — allow through,
                        // the web layer handles password entry
                        self.isAuthenticated = true
                        self.setWebViewInteraction(enabled: true)
                        AppSwitcherGuard.shared.removeBiometricHold()
                        completion(true)
                    default:
                        // Auth failed — keep blur visible
                        completion(false)
                    }
                }
            }
        }
    }

    /// Enable or disable user interaction on the WebView to prevent bypass
    /// of the biometric overlay via accessibility, keyboard, or VoiceOver.
    private func setWebViewInteraction(enabled: Bool) {
        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first,
            let rootVC = scene.windows.first?.rootViewController as? CAPBridgeViewController,
            let webView = rootVC.webView else { return }
        webView.isUserInteractionEnabled = enabled
    }

    @objc private func appDidEnterBackground() {
        // Reset so next foreground requires re-auth
        isAuthenticated = false
    }
}

// MARK: - AppSwitcherGuard Extension

extension AppSwitcherGuard {
    /// Called by BiometricAuthManager after successful authentication.
    /// Only removes the blur if biometric auth is the current hold reason.
    func holdForBiometric() {
        // Don't remove blur in didBecomeActive — biometric will manage it
    }

    func removeBiometricHold() {
        // Remove blur overlay and re-enable WebView interaction after biometric success
        DispatchQueue.main.async {
            // Access the blur view through the window
            if let scene = UIApplication.shared.connectedScenes
                .compactMap({ $0 as? UIWindowScene })
                .first,
                let window = scene.windows.first {
                if let blur = window.viewWithTag(999_888) {
                    blur.removeFromSuperview()
                }
                // Ensure WebView interaction is restored
                if let rootVC = window.rootViewController as? CAPBridgeViewController,
                   let webView = rootVC.webView {
                    webView.isUserInteractionEnabled = true
                }
            }
        }
    }
}

