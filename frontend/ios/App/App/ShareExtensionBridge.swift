import Foundation
import Capacitor

/// Capacitor plugin that bridges auth tokens from the main app's storage
/// into the shared App Group UserDefaults, allowing the Share Extension
/// to authenticate with the Perennia AI API.
///
/// Also processes any pending uploads that were queued by the Share Extension
/// when uploads failed (e.g., due to network issues).
@objc(ShareExtensionBridge)
class ShareExtensionBridge: CAPPlugin, CAPBridgedPlugin {

    let identifier = "ShareExtensionBridge"
    let jsName = "ShareExtensionBridge"
    let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "syncAuthToken", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getPendingUploads", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearPendingUpload", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getSharedItems", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clearSharedItem", returnType: CAPPluginReturnPromise),
    ]

    private static let appGroupID = "group.com.perenniaai.crm"

    /// Called from JavaScript whenever the auth token changes (login, refresh, logout).
    /// Stores the token in the iOS Keychain (shared access group) so the Share Extension can read it.
    @objc func syncAuthToken(_ call: CAPPluginCall) {
        let token = call.getString("token") ?? ""

        if token.isEmpty {
            KeychainService.shared.authToken = nil
        } else {
            // Store in both app-private and shared Keychain (authToken setter does both)
            KeychainService.shared.authToken = token
        }

        call.resolve(["synced": true])
    }

    /// Returns the list of pending uploads queued by the Share Extension.
    /// The main app can retry these uploads via its own network stack.
    @objc func getPendingUploads(_ call: CAPPluginCall) {
        guard let sharedDefaults = UserDefaults(suiteName: ShareExtensionBridge.appGroupID) else {
            call.resolve(["uploads": []])
            return
        }

        guard let data = sharedDefaults.data(forKey: "PendingShareUploads") else {
            call.resolve(["uploads": []])
            return
        }

        // Decode and return as JSON-compatible array
        if let uploads = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
            call.resolve(["uploads": uploads])
        } else {
            call.resolve(["uploads": []])
        }
    }

    /// Removes a pending upload after it has been successfully retried.
    @objc func clearPendingUpload(_ call: CAPPluginCall) {
        guard let uploadId = call.getString("id") else {
            call.reject("Missing upload id")
            return
        }

        guard let sharedDefaults = UserDefaults(suiteName: ShareExtensionBridge.appGroupID) else {
            call.reject("Failed to access App Group UserDefaults")
            return
        }

        guard let data = sharedDefaults.data(forKey: "PendingShareUploads"),
              var uploads = try? JSONDecoder().decode([PendingUploadEntry].self, from: data) else {
            call.resolve(["removed": false])
            return
        }

        let countBefore = uploads.count
        uploads.removeAll { $0.id == uploadId }

        // Remove the queued file from the App Group container
        if let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: ShareExtensionBridge.appGroupID
        ) {
            // Find the entry that was removed to get its path
            if let originalData = try? JSONDecoder().decode([PendingUploadEntry].self, from: data),
               let removed = originalData.first(where: { $0.id == uploadId }) {
                let fileURL = containerURL.appendingPathComponent(removed.relativePath)
                try? FileManager.default.removeItem(at: fileURL)
            }
        }

        if let newData = try? JSONEncoder().encode(uploads) {
            sharedDefaults.set(newData, forKey: "PendingShareUploads")
        }

        call.resolve(["removed": uploads.count < countBefore])
    }

    // MARK: - Shared Text/URL Items

    /// Returns text/URL items shared via the share extension (links, text snippets).
    @objc func getSharedItems(_ call: CAPPluginCall) {
        guard let sharedDefaults = UserDefaults(suiteName: ShareExtensionBridge.appGroupID) else {
            call.resolve(["items": []])
            return
        }

        guard let data = sharedDefaults.data(forKey: "PendingSharedItems") else {
            call.resolve(["items": []])
            return
        }

        if let items = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
            call.resolve(["items": items])
        } else {
            call.resolve(["items": []])
        }
    }

    /// Removes a shared text/URL item after it has been processed by the main app.
    @objc func clearSharedItem(_ call: CAPPluginCall) {
        guard let itemId = call.getString("id") else {
            call.reject("Missing item id")
            return
        }

        guard let sharedDefaults = UserDefaults(suiteName: ShareExtensionBridge.appGroupID) else {
            call.reject("Failed to access App Group UserDefaults")
            return
        }

        guard let data = sharedDefaults.data(forKey: "PendingSharedItems"),
              var items = try? JSONSerialization.jsonObject(with: data) as? [[String: String]] else {
            call.resolve(["removed": false])
            return
        }

        let countBefore = items.count
        items.removeAll { $0["id"] == itemId }

        if let newData = try? JSONSerialization.data(withJSONObject: items) {
            sharedDefaults.set(newData, forKey: "PendingSharedItems")
        }

        call.resolve(["removed": items.count < countBefore])
    }
}

// Mirror of the struct used in ShareNetworkService.swift
private struct PendingUploadEntry: Codable {
    let id: String
    let fileName: String
    let mimeType: String
    let loanID: Int
    let borrowerID: Int
    let docType: String?
    let queuedAt: Date
    let relativePath: String
}
