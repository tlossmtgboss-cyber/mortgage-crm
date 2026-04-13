/**
 * SensitiveScreenPlugin.swift
 * Perennia AI — Screen Recording Prevention for Sensitive Screens
 *
 * Capacitor plugin that monitors UIScreen.main.isCaptured and overlays
 * a blur/blank view when screen recording is active while the user is
 * on a sensitive screen (SSN entry, income entry, compliance forms).
 *
 * The WebView calls enterSensitiveScreen / leaveSensitiveScreen via the
 * Capacitor bridge. While at least one sensitive screen is active,
 * the plugin observes UIScreen.capturedDidChangeNotification and
 * UIApplication.userDidTakeScreenshotNotification to respond to
 * recording and screenshot events.
 *
 * GLBA / SOC 2 compliance: NPI (SSN, income, financial data) must not
 * be captured in screen recordings or screenshots.
 */

import Foundation
import UIKit
import Capacitor
import os.log

@objc(SensitiveScreenPlugin)
public class SensitiveScreenPlugin: CAPPlugin, CAPBridgedPlugin {

    public let identifier = "SensitiveScreenPlugin"
    public let jsName = "SensitiveScreen"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "enterSensitiveScreen", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "leaveSensitiveScreen", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getStatus", returnType: CAPPluginReturnPromise)
    ]

    // MARK: - State

    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "SensitiveScreen")

    /// Names of currently active sensitive screens (supports nesting)
    private var activeScreens: [String] = []

    /// The blur overlay view, if currently displayed
    private var captureOverlay: UIView?

    /// Whether we are currently observing capture notifications
    private var isObserving = false

    // MARK: - Plugin Methods

    @objc func enterSensitiveScreen(_ call: CAPPluginCall) {
        let screen = call.getString("screen") ?? "unknown"

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            self.activeScreens.append(screen)
            os_log(.info, log: self.log, "Entered sensitive screen: %{public}@  (active: %d)", screen, self.activeScreens.count)

            if !self.isObserving {
                self.startObserving()
            }

            // If screen is already being captured, show overlay immediately
            if UIScreen.main.isCaptured {
                self.showCaptureOverlay()
            }
        }

        call.resolve(["active": true, "screen": screen])
    }

    @objc func leaveSensitiveScreen(_ call: CAPPluginCall) {
        let screen = call.getString("screen") ?? "unknown"

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            // Remove the first matching screen name (supports duplicates)
            if let index = self.activeScreens.firstIndex(of: screen) {
                self.activeScreens.remove(at: index)
            }

            os_log(.info, log: self.log, "Left sensitive screen: %{public}@  (active: %d)", screen, self.activeScreens.count)

            if self.activeScreens.isEmpty {
                self.stopObserving()
                self.removeCaptureOverlay()
            }
        }

        call.resolve(["active": !activeScreens.isEmpty, "screen": screen])
    }

    @objc func getStatus(_ call: CAPPluginCall) {
        call.resolve([
            "isCaptured": UIScreen.main.isCaptured,
            "sensitiveScreenActive": !activeScreens.isEmpty,
            "activeScreens": activeScreens
        ])
    }

    // MARK: - Notification Observers

    private func startObserving() {
        guard !isObserving else { return }
        isObserving = true

        // Screen recording started/stopped
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(capturedDidChange),
            name: UIScreen.capturedDidChangeNotification,
            object: nil
        )

        // User took a screenshot
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(userDidTakeScreenshot),
            name: UIApplication.userDidTakeScreenshotNotification,
            object: nil
        )

        os_log(.info, log: log, "Started observing screen capture events")
    }

    private func stopObserving() {
        guard isObserving else { return }
        isObserving = false

        NotificationCenter.default.removeObserver(self, name: UIScreen.capturedDidChangeNotification, object: nil)
        NotificationCenter.default.removeObserver(self, name: UIApplication.userDidTakeScreenshotNotification, object: nil)

        os_log(.info, log: log, "Stopped observing screen capture events")
    }

    // MARK: - Capture Event Handlers

    @objc private func capturedDidChange(_ notification: Notification) {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            if UIScreen.main.isCaptured {
                os_log(.error, log: self.log, "Screen recording detected on sensitive screen!")
                self.showCaptureOverlay()
                self.notifyWebView(event: "screenRecordingStarted")

                AuditLogger.shared.log(event: .securityViolation, details: [
                    "type": "screen_recording_on_sensitive_screen",
                    "active_screens": self.activeScreens.joined(separator: ", ")
                ])
            } else {
                os_log(.info, log: self.log, "Screen recording stopped")
                self.removeCaptureOverlay()
                self.notifyWebView(event: "screenRecordingStopped")
            }
        }
    }

    @objc private func userDidTakeScreenshot(_ notification: Notification) {
        guard !activeScreens.isEmpty else { return }

        os_log(.error, log: log, "Screenshot taken on sensitive screen!")

        AuditLogger.shared.log(event: .securityViolation, details: [
            "type": "screenshot_on_sensitive_screen",
            "active_screens": activeScreens.joined(separator: ", ")
        ])

        notifyWebView(event: "screenshotTaken")
    }

    // MARK: - Capture Overlay

    private func showCaptureOverlay() {
        guard captureOverlay == nil else { return }

        guard let window = self.bridge?.viewController?.view.window else {
            os_log(.error, log: log, "Cannot show capture overlay: no window available")
            return
        }

        let overlay = UIView(frame: window.bounds)
        overlay.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        overlay.tag = 999_777  // Distinct from AppSwitcherGuard's tag (999_888)

        // Heavy blur effect
        let blurEffect = UIBlurEffect(style: .systemThickMaterial)
        let blurView = UIVisualEffectView(effect: blurEffect)
        blurView.frame = overlay.bounds
        blurView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        overlay.addSubview(blurView)

        // Warning label
        let warningStack = UIStackView()
        warningStack.axis = .vertical
        warningStack.alignment = .center
        warningStack.spacing = 12
        warningStack.translatesAutoresizingMaskIntoConstraints = false

        let iconLabel = UILabel()
        iconLabel.text = "\u{1F6E1}"  // shield emoji
        iconLabel.font = .systemFont(ofSize: 48)
        iconLabel.textAlignment = .center

        let titleLabel = UILabel()
        titleLabel.text = "Screen Recording Blocked"
        titleLabel.font = .systemFont(ofSize: 22, weight: .bold)
        titleLabel.textColor = .label
        titleLabel.textAlignment = .center

        let messageLabel = UILabel()
        messageLabel.text = "This screen contains sensitive financial data.\nScreen recording is not permitted."
        messageLabel.font = .systemFont(ofSize: 15, weight: .regular)
        messageLabel.textColor = .secondaryLabel
        messageLabel.textAlignment = .center
        messageLabel.numberOfLines = 0

        warningStack.addArrangedSubview(iconLabel)
        warningStack.addArrangedSubview(titleLabel)
        warningStack.addArrangedSubview(messageLabel)

        blurView.contentView.addSubview(warningStack)
        NSLayoutConstraint.activate([
            warningStack.centerXAnchor.constraint(equalTo: blurView.contentView.centerXAnchor),
            warningStack.centerYAnchor.constraint(equalTo: blurView.contentView.centerYAnchor),
            warningStack.leadingAnchor.constraint(greaterThanOrEqualTo: blurView.contentView.leadingAnchor, constant: 32),
            warningStack.trailingAnchor.constraint(lessThanOrEqualTo: blurView.contentView.trailingAnchor, constant: -32)
        ])

        // Accessibility
        overlay.isAccessibilityElement = true
        overlay.accessibilityLabel = "Screen content hidden. Screen recording is not permitted on this screen."
        overlay.accessibilityTraits = .staticText

        window.addSubview(overlay)
        self.captureOverlay = overlay

        UIAccessibility.post(notification: .screenChanged, argument: overlay)

        os_log(.info, log: log, "Capture overlay displayed")
    }

    private func removeCaptureOverlay() {
        guard let overlay = captureOverlay else { return }

        overlay.removeFromSuperview()
        captureOverlay = nil

        UIAccessibility.post(notification: .screenChanged, argument: nil)

        os_log(.info, log: log, "Capture overlay removed")
    }

    // MARK: - WebView Notification

    private func notifyWebView(event: String) {
        notifyListeners(event, data: [
            "isCaptured": UIScreen.main.isCaptured,
            "activeScreens": activeScreens,
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ])
    }

    // MARK: - Cleanup

    deinit {
        stopObserving()
        DispatchQueue.main.async { [weak overlay = captureOverlay] in
            overlay?.removeFromSuperview()
        }
    }
}
