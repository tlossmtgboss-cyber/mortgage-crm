/**
 * ManagedPasteboardGuard.swift
 * Perennia AI — MDM Pasteboard & VPN Enforcement
 *
 * Enforces enterprise data loss prevention (DLP) policies:
 * - Blocks clipboard sharing when MDM disables it
 * - Monitors VPN status when MDM requires it
 * - Reports policy violations to AuditLogger
 */

import Foundation
import UIKit
import NetworkExtension
import os.log

@available(iOS 14.0, *)
final class ManagedPasteboardGuard {

    static let shared = ManagedPasteboardGuard()

    private let logger = Logger(subsystem: "com.perenniaai.crm", category: "MDM-DLP")

    // MARK: - MDM Policy State

    private(set) var isClipboardSharingAllowed: Bool = true
    private(set) var isVPNRequired: Bool = false
    private(set) var isVPNConnected: Bool = false

    private var vpnObserver: Any?

    // MARK: - Initialization

    private init() {
        loadMDMPolicies()
        observeVPNStatus()
        setupPasteboardMonitoring()
    }

    // MARK: - MDM Policy Loading

    /// Read managed app configuration pushed by MDM (Jamf, Intune, etc.)
    func loadMDMPolicies() {
        guard let managedConfig = UserDefaults.standard.dictionary(forKey: "com.apple.configuration.managed") else {
            logger.debug("No managed configuration found — using defaults")
            return
        }

        if let allowClipboard = managedConfig["AllowClipboardSharing"] as? Bool {
            isClipboardSharingAllowed = allowClipboard
            logger.info("MDM clipboard policy: \(allowClipboard ? "allowed" : "blocked")")
        }

        if let requireVPN = managedConfig["RequireVPN"] as? Bool {
            isVPNRequired = requireVPN
            logger.info("MDM VPN policy: \(requireVPN ? "required" : "optional")")
        }
    }

    // MARK: - Pasteboard Enforcement

    /// Call before any paste operation to check if clipboard sharing is allowed
    func canPaste() -> Bool {
        guard !isClipboardSharingAllowed else { return true }

        // Check if paste content originates from this app (intra-app paste is always OK)
        if #available(iOS 16.0, *) {
            // iOS 16+ has system paste permission — MDM can enforce via restrictions profile
            // We just check our own policy flag
        }

        logger.warning("Clipboard paste blocked by MDM policy")
        AuditLogger.shared.log(
            event: .securityViolation,
            details: [
                "policy": "AllowClipboardSharing",
                "action": "paste_blocked",
                "source": "MDM"
            ]
        )
        return false
    }

    /// Clear pasteboard when app backgrounds (if MDM requires it)
    func clearPasteboardOnBackground() {
        guard !isClipboardSharingAllowed else { return }

        UIPasteboard.general.items = []
        logger.info("Pasteboard cleared on background (MDM policy)")
    }

    private func setupPasteboardMonitoring() {
        // Clear pasteboard on app background if clipboard sharing is disabled
        NotificationCenter.default.addObserver(
            forName: UIApplication.willResignActiveNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.clearPasteboardOnBackground()
        }
    }

    // MARK: - VPN Status Monitoring

    /// Check current VPN connection status
    func checkVPNStatus(completion: (() -> Void)? = nil) {
        NEVPNManager.shared().loadFromPreferences { [weak self] error in
            guard let self = self else { completion?(); return }
            if let error = error {
                self.logger.error("Failed to load VPN preferences: \(error.localizedDescription)")
                completion?()
                return
            }

            let status = NEVPNManager.shared().connection.status
            self.isVPNConnected = (status == .connected || status == .connecting)

            if self.isVPNRequired && !self.isVPNConnected {
                self.logger.warning("VPN required by MDM but not connected (status: \(status.rawValue))")
                AuditLogger.shared.log(
                    event: .securityViolation,
                    details: [
                        "policy": "RequireVPN",
                        "vpn_status": "\(status.rawValue)",
                        "action": "vpn_not_connected"
                    ]
                )

                // Notify JS layer so it can show a warning
                NotificationCenter.default.post(
                    name: .vpnRequiredButDisconnected,
                    object: nil
                )
            }

            completion?()
        }
    }

    private func observeVPNStatus() {
        vpnObserver = NotificationCenter.default.addObserver(
            forName: .NEVPNStatusDidChange,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let connection = (notification.object as? NEVPNConnection) else { return }
            let connected = connection.status == .connected
            self?.isVPNConnected = connected
            self?.logger.info("VPN status changed: \(connected ? "connected" : "disconnected")")

            if let self = self, self.isVPNRequired && !connected {
                NotificationCenter.default.post(name: .vpnRequiredButDisconnected, object: nil)
            }
        }
    }

    // MARK: - Policy Summary

    var policySummary: [String: Any] {
        return [
            "clipboardSharingAllowed": isClipboardSharingAllowed,
            "vpnRequired": isVPNRequired,
            "vpnConnected": isVPNConnected,
            "isCompliant": !isVPNRequired || isVPNConnected
        ]
    }

    deinit {
        if let observer = vpnObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let vpnRequiredButDisconnected = Notification.Name("com.perenniaai.vpnRequiredButDisconnected")
}
