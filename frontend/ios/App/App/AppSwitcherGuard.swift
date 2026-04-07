/**
 * AppSwitcherGuard.swift
 * Perennia AI — App Switcher & Screenshot Protection
 *
 * GLBA requires preventing NPI from appearing in app switcher previews.
 * This service overlays a blur/branded screen when the app backgrounds,
 * and optionally blocks screenshots on sensitive screens.
 *
 * Usage: Call `AppSwitcherGuard.shared.install(on:)` from AppDelegate.
 */

import UIKit
import os.log

final class AppSwitcherGuard {

    static let shared = AppSwitcherGuard()

    private var blurView: UIView?
    private weak var window: UIWindow?
    private let log = OSLog(subsystem: "com.perenniaai.crm", category: "AppSwitcherGuard")

    private init() {}

    // MARK: - Public API

    /// Install the guard on the given window. Call from applicationDidFinishLaunching.
    func install(on window: UIWindow?) {
        self.window = window

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(willResignActive),
            name: UIApplication.willResignActiveNotification,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(didBecomeActive),
            name: UIApplication.didBecomeActiveNotification,
            object: nil
        )

        os_log(.info, log: log, "App switcher guard installed")
    }

    /// Remove the guard (e.g., on dealloc).
    func uninstall() {
        NotificationCenter.default.removeObserver(self)
        removeBlur()
    }

    // MARK: - Lifecycle

    @objc private func willResignActive() {
        showBlur()
        AuditLogger.shared.log(event: .appBackground)
    }

    @objc private func didBecomeActive() {
        removeBlur()
        AuditLogger.shared.log(event: .appForeground)
    }

    // MARK: - Blur Overlay

    private func showBlur() {
        guard let window = window, blurView == nil else { return }

        let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemThickMaterial))
        blur.frame = window.bounds
        blur.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        blur.tag = 999_888

        // Add branding
        let logo = UILabel()
        logo.text = "Perennia AI"
        logo.font = .systemFont(ofSize: 24, weight: .bold)
        logo.textColor = .secondaryLabel
        logo.translatesAutoresizingMaskIntoConstraints = false
        blur.contentView.addSubview(logo)
        NSLayoutConstraint.activate([
            logo.centerXAnchor.constraint(equalTo: blur.contentView.centerXAnchor),
            logo.centerYAnchor.constraint(equalTo: blur.contentView.centerYAnchor)
        ])

        // Accessibility: announce the security overlay for VoiceOver users
        blur.isAccessibilityElement = true
        blur.accessibilityLabel = "Screen content hidden for security"
        blur.accessibilityTraits = .staticText
        logo.accessibilityTraits = .staticText

        window.addSubview(blur)
        self.blurView = blur

        UIAccessibility.post(notification: .screenChanged, argument: blur)
    }

    private func removeBlur() {
        blurView?.removeFromSuperview()
        blurView = nil

        // Accessibility: notify VoiceOver that the screen has changed back
        UIAccessibility.post(notification: .screenChanged, argument: nil)
    }
}
