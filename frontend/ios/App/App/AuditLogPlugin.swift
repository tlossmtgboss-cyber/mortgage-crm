/**
 * AuditLogPlugin.swift
 * Perennia AI — Capacitor Bridge for AuditLogger
 *
 * Exposes the encrypted audit trail (AuditLogger.swift) to the JavaScript
 * layer via Capacitor plugin methods. All security-relevant events logged
 * from the React app flow through this bridge into the local encrypted
 * audit log and can be synced to the backend in batches.
 *
 * Methods available from JavaScript:
 *   - AuditLog.logEvent({ event, details })     — log a security event
 *   - AuditLog.getRecentLogs({ limit? })         — get last N entries (default 50)
 *   - AuditLog.syncToBackend()                   — sync unsynced entries to backend
 *   - AuditLog.getUnsyncedCount()                — get count of unsynced entries
 *   - AuditLog.verifyIntegrity()                 — verify hash chain integrity
 */

import Foundation
import Capacitor

@available(iOS 14.0, *)
@objc(AuditLogPlugin)
public class AuditLogPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "AuditLogPlugin"
    public let jsName = "AuditLog"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "logEvent", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getRecentLogs", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "syncToBackend", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getUnsyncedCount", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "verifyIntegrity", returnType: CAPPluginReturnPromise),
    ]

    @objc func logEvent(_ call: CAPPluginCall) {
        guard let eventType = call.getString("event"),
              let event = AuditLogger.EventType(rawValue: eventType) else {
            call.reject("Invalid event type")
            return
        }

        let details = call.getObject("details") as? [String: String] ?? [:]
        AuditLogger.shared.log(event: event, details: details)
        call.resolve()
    }

    @objc func getRecentLogs(_ call: CAPPluginCall) {
        let limit = call.getInt("limit") ?? 50
        let logs = AuditLogger.shared.getRecentLogs(limit: limit)
        let mapped = logs.map { entry -> [String: Any] in
            return [
                "id": entry.id,
                "timestamp": entry.timestamp,
                "event": entry.event.rawValue,
                "details": entry.details,
                "synced": entry.synced,
                "previousHash": entry.previousHash,
                "hash": entry.hash
            ]
        }
        call.resolve(["logs": mapped])
    }

    @objc func syncToBackend(_ call: CAPPluginCall) {
        Task {
            let count = await AuditLogger.shared.syncToBackend()
            call.resolve(["synced": count])
        }
    }

    @objc func getUnsyncedCount(_ call: CAPPluginCall) {
        call.resolve(["count": AuditLogger.shared.unsyncedCount])
    }

    @objc func verifyIntegrity(_ call: CAPPluginCall) {
        let result = AuditLogger.shared.verifyChainIntegrity()
        var response: [String: Any] = [
            "valid": result.valid,
            "totalEntries": AuditLogger.shared.getRecentLogs(limit: Int.max).count
        ]
        if let brokenAt = result.brokenAt {
            response["brokenAt"] = brokenAt
        }
        call.resolve(response)
    }
}
